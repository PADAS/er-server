from __future__ import annotations

from datetime import datetime

from django.db.models import Count, Max, Q, QuerySet

from accounts.models import User
from activity.models import EventType
from choices.etags import get_event_choices_version
from mapping.models import SpatialFeature
from observations.models import Source, Subject


def _timestamped_model_version(queryset: QuerySet, *, count_active: bool = False) -> str:
    """Cheap change-detection token for a ``TimestampedModel`` queryset.

    One aggregate query producing ``total`` (``Count("id")``) and
    ``latest_update`` (``Max("updated_at")``), which together change on row
    creation and on any per-instance ``.save()`` edit (``updated_at`` has
    ``auto_now=True``). When ``count_active`` is set, an ``active`` component
    (``Count("id", filter=Q(is_active=True))``) is added too, since a bulk
    ``QuerySet.update(is_active=...)`` bypasses ``auto_now`` and would
    otherwise be invisible to ``total``/``latest_update`` - the same landmine
    documented in ``choices.etags.get_event_choices_version``.
    """
    aggregates: dict[str, object] = {"total": Count("id"), "latest_update": Max("updated_at")}
    if count_active:
        aggregates["active"] = Count("id", filter=Q(is_active=True))

    result = queryset.aggregate(**aggregates)
    total = result["total"] or 0
    latest_update: datetime | None = result["latest_update"]
    parts = [str(total), latest_update.isoformat() if latest_update else "none"]
    if count_active:
        parts.append(str(result["active"] or 0))
    return ":".join(parts)


def _users_version() -> str:
    """Cheap change-detection token for the ``User`` model.

    ``User`` has no ``updated_at`` field (only ``date_joined``), so this can't
    use the ``TimestampedModel`` shape. Deliberately does NOT use
    ``last_login`` - it churns on every sign-in and would defeat caching for
    an unrelated field.

    Aggregates ``total`` (``Count("id")``), ``latest_joined``
    (``Max("date_joined")``), and ``active`` (``Count("id",
    filter=Q(is_active=True))``) in one query.

    What this catches: new users (``total``/``latest_joined`` change), and a
    user being activated/deactivated (``active`` changes).

    What this misses: edits to an existing, still-active user that don't
    change ``is_active`` - e.g. renaming a user (``first_name``/``last_name``,
    which feed ``UsersDynamicSchemaView.get_display_name_from_item``), or
    changing ``email``/``username``. There is no cheap, reliably-updated
    per-row timestamp to detect those without adding a migration, so this is
    a deliberate coverage gap versus the other models here.
    """
    aggregates = User.objects.aggregate(
        total=Count("id"),
        latest_joined=Max("date_joined"),
        active=Count("id", filter=Q(is_active=True)),
    )
    total = aggregates["total"] or 0
    latest_joined: datetime | None = aggregates["latest_joined"]
    active = aggregates["active"] or 0
    return f"{total}:{latest_joined.isoformat() if latest_joined else 'none'}:{active}"


def get_dynamic_schema_sources_version() -> str:
    """Cache-busting token that changes whenever any dynamic schema data source changes.

    A rendered V2 event-type schema can ``$ref`` any of the
    ``DynamicSchemaFromSourceView`` subclasses in ``schemas/views.py``: Users,
    Sources, Subjects, Choices, Spatial Features, and (for community input)
    Event Types themselves. An ETag salted only with the Choices version (see
    ``choices.etags.get_event_choices_version``) is therefore stale whenever a
    Subject is renamed, a Source is added, a user is created, etc. - the
    rendered schema changes but the ETag doesn't, so clients keep serving a
    cached response.

    This combines a lightweight version token per source model - one
    aggregate query each - into a single string. Tenant-scoping is automatic
    under request context via each model's manager; callers must not add
    tenant filters or tenant IDs themselves (see the cache-key guidance in
    AGENTS.md).

    Trade-off: this is intentionally coarse. It changes on *any* row of a
    given model changing, not just rows actually referenced by a given
    schema, so unrelated churn (e.g. any Subject being renamed) invalidates
    every event type's ETag rather than just the ones that reference
    Subjects. That's an acceptable cost for correctness - false-positive
    invalidation only costs an extra render, whereas a stale ETag serves
    wrong data indefinitely.
    """
    versions = [
        get_event_choices_version(),
        _users_version(),
        _timestamped_model_version(Source.objects.all()),
        _timestamped_model_version(Subject.objects.all(), count_active=True),
        _timestamped_model_version(SpatialFeature.objects.all()),
        _timestamped_model_version(EventType.objects.all(), count_active=True),
    ]
    return ":".join(versions)
