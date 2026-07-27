"""Rebuild ``activity_tsvectormodel.tsvector_event`` from current event data.

Migration ``0205_remove_schema_from_tsvector_triggers`` stopped the Postgres
triggers from folding the event type's JSON schema into the event search vector
(ERA-13500), but existing rows keep the polluted vector until something touches
the event. This module recomputes them with the corrected formula. It is driven
by the ``rebuild_event_tsvectors`` management command as a post-deploy step, and
can be re-run against a single site on demand.

Everything here is raw SQL, deliberately:

* Management commands run with **no tenant context** by default, and
  ``activity_tsvectormodel`` reuses ``id`` across tenants in production (the
  physical primary key is the composite ``(das_tenant_id, id)``). An ORM write
  keyed on ``id`` alone would overwrite every tenant's row sharing that id, so
  every statement below names ``das_tenant_id`` in its own predicates -- see
  AGENTS.md, "Writes under unset/absent tenant context".
* Raw SQL is not tenant-scoped, which is what makes the all-tenants walk
  possible; the tenant predicates are supplied here rather than inherited.

The table is walked with keyset pagination over ``(das_tenant_id, event_id)``
-- the columns of the ``activity_tsvectormodel_unique`` constraint, so the key
is unique and the walk cannot revisit or skip a row. Each batch is its own
statement, so no single table-wide lock is taken.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable
from uuid import UUID

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 2000
LOG_EVERY_N_BATCHES = 10

KeysetCursor = tuple[UUID, UUID]

# Same expression the 0205 triggers build, with one deliberate difference: the
# event details term is coalesced. The triggers only ever fire with a details row
# in hand, but a rebuild also visits events whose details row is missing or whose
# data has no "event_details" key -- without the coalesce, `#>>` returns NULL and
# NULL-concatenation would wipe the whole vector.
TSVECTOR_EVENT_EXPRESSION = """
    setweight(to_tsvector(et.display)::tsvector, 'A') ||
    setweight(to_tsvector(coalesce(e.title, '')), 'B') ||
    setweight(to_tsvector(coalesce(ed.data #>> '{event_details}', '')), 'A')
"""

# The joins carry the tenant predicate on the write: `ts.das_tenant_id =
# e.das_tenant_id` scopes the UPDATE, and joining activity_eventtype on
# das_tenant_id as well as id keeps a shared event type id from matching one row
# per tenant. The lateral subquery picks the newest EventDetails row, which is
# the one the application treats as current.
_REBUILD_BATCH_HEAD = f"""
UPDATE activity_tsvectormodel ts
SET tsvector_event = {TSVECTOR_EVENT_EXPRESSION}
FROM activity_event e
         JOIN activity_eventtype et
              ON et.id = e.event_type_id
                  AND et.das_tenant_id = e.das_tenant_id
         LEFT JOIN LATERAL (
    SELECT ed.data
    FROM activity_eventdetails ed
    WHERE ed.event_id = e.id
      AND ed.das_tenant_id = e.das_tenant_id
    ORDER BY ed.updated_at DESC
    LIMIT 1
    ) ed ON TRUE
"""


def build_upper_bound_query(
    *,
    cursor_key: KeysetCursor | None,
    das_tenant_id: UUID | str | None,
    batch_size: int,
) -> tuple[str, list[object]]:
    """Query for the last key of the next batch, in keyset order.

    Taking only the batch's upper bound lets the UPDATE address the batch as a
    range instead of shipping a list of ids back to Postgres. Returns no row once
    the walk is exhausted.
    """
    predicates: list[str] = []
    params: list[object] = []
    if das_tenant_id is not None:
        predicates.append("das_tenant_id = %s::uuid")
        params.append(str(das_tenant_id))
    if cursor_key is not None:
        predicates.append("(das_tenant_id, event_id) > (%s::uuid, %s::uuid)")
        params.extend(str(value) for value in cursor_key)
    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    params.append(batch_size)

    sql = f"""
SELECT das_tenant_id, event_id
FROM (
    SELECT das_tenant_id, event_id
    FROM activity_tsvectormodel
    {where}
    ORDER BY das_tenant_id, event_id
    LIMIT %s
) batch
ORDER BY das_tenant_id DESC, event_id DESC
LIMIT 1
"""
    return sql, params


def build_rebuild_batch_query(
    *,
    upper_bound: KeysetCursor,
    cursor_key: KeysetCursor | None,
    das_tenant_id: UUID | str | None,
) -> tuple[str, list[object]]:
    """UPDATE that rebuilds every row in ``(cursor_key, upper_bound]``.

    ``das_tenant_id`` is always part of the ``WHERE`` -- via
    ``ts.das_tenant_id = e.das_tenant_id`` for an all-tenants walk, and
    additionally pinned to one tenant when ``das_tenant_id`` is given.
    """
    predicates = [
        "ts.event_id = e.id",
        "ts.das_tenant_id = e.das_tenant_id",
        "(ts.das_tenant_id, ts.event_id) <= (%s::uuid, %s::uuid)",
    ]
    params: list[object] = [str(value) for value in upper_bound]
    if das_tenant_id is not None:
        predicates.append("ts.das_tenant_id = %s::uuid")
        params.append(str(das_tenant_id))
    if cursor_key is not None:
        predicates.append("(ts.das_tenant_id, ts.event_id) > (%s::uuid, %s::uuid)")
        params.extend(str(value) for value in cursor_key)

    sql = _REBUILD_BATCH_HEAD + "WHERE " + "\n  AND ".join(predicates)
    return sql, params


def rebuild_event_tsvectors(
    connection: BaseDatabaseWrapper,
    *,
    das_tenant_id: UUID | str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    progress_callback: Callable[[int, int], None] | None = None,
) -> int:
    """Recompute ``tsvector_event``, one keyset batch per statement.

    Pass ``das_tenant_id`` to restrict both the walk and the write to a single
    tenant; omit it to walk every tenant. ``progress_callback`` is invoked with
    ``(rows_updated, batches)`` every ``LOG_EVERY_N_BATCHES`` batches so a caller
    can surface progress during a long run.

    Returns the number of rows updated. Rows whose event no longer exists (or
    whose event type row is missing for that tenant) are skipped by the joins but
    still advance the cursor, so a stale row cannot stall the walk.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    cursor_key: KeysetCursor | None = None
    batches = 0
    rows_updated = 0

    logger.info(
        "Rebuilding activity_tsvectormodel.tsvector_event (tenant=%s, batch size %s)",
        das_tenant_id or "ALL",
        batch_size,
    )

    with connection.cursor() as cursor:
        while True:
            bound_sql, bound_params = build_upper_bound_query(
                cursor_key=cursor_key, das_tenant_id=das_tenant_id, batch_size=batch_size
            )
            cursor.execute(bound_sql, bound_params)
            upper_bound = cursor.fetchone()
            if upper_bound is None:
                break

            update_sql, update_params = build_rebuild_batch_query(
                upper_bound=upper_bound, cursor_key=cursor_key, das_tenant_id=das_tenant_id
            )
            cursor.execute(update_sql, update_params)

            rows_updated += cursor.rowcount
            batches += 1
            cursor_key = (upper_bound[0], upper_bound[1])

            if batches % LOG_EVERY_N_BATCHES == 0:
                logger.info("Rebuilt %s event tsvectors across %s batches", rows_updated, batches)
                if progress_callback is not None:
                    progress_callback(rows_updated, batches)

    logger.info(
        "Finished rebuilding %s event tsvectors across %s batches (tenant=%s)",
        rows_updated,
        batches,
        das_tenant_id or "ALL",
    )
    return rows_updated
