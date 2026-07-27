from __future__ import annotations

from django.db.models import Count, Max, Q

from choices.models import Choice


def get_event_choices_version() -> str:
    """Cache-busting token that changes whenever any event Choice changes.

    Tenant-scoped automatically via the manager under request context.
    ``Choice.objects`` is not filtered by ``is_active``, so soft-deleted rows
    are included in these aggregates - required for ``active``/``latest_delete``
    below to see them.

    Four components are aggregated in a single query, each covering a distinct
    write path:

    - ``total``: ``Count("id")`` over all rows (active and inactive). Changes on
      create (and any hard delete).
    - ``active``: ``Count("id", filter=Q(is_active=True))``. ``ChoiceQuerySet.
      disable_choices()``/``soft_delete()`` (used by bulk admin actions) perform
      a bulk ``QuerySet.update(delete_on=..., is_active=False)``. Django's
      ``QuerySet.update()`` does NOT trigger ``auto_now``, and the row is a soft
      delete so it still exists - meaning ``total`` and ``latest_update`` (below)
      are both unchanged by a bulk soft-delete or bulk re-enable. ``active`` is
      the only component that reliably changes on this path, in either direction.
    - ``latest_update``: ``Max("updated_at")``. Changes on a per-instance
      ``.save()`` edit (e.g. ``Choice.disable()``, or any other field edit),
      since ``updated_at`` has ``auto_now=True`` and ``.save()`` does fire it.
    - ``latest_delete``: ``Max("delete_on")``. Belt-and-suspenders coverage for
      soft-delete timing - ``delete_on`` is set by both the per-instance and
      bulk soft-delete paths, so it changes even in cases where ``active``
      alone might not distinguish (e.g. a delete followed by a re-create in the
      same aggregate window).
    """
    aggregates = Choice.objects.filter(model=Choice.EVENT_MODEL).aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        latest_update=Max("updated_at"),
        latest_delete=Max("delete_on"),
    )
    total = aggregates["total"] or 0
    active = aggregates["active"] or 0
    latest_update = aggregates["latest_update"]
    latest_delete = aggregates["latest_delete"]
    return (
        f"{total}:{active}:"
        f"{latest_update.isoformat() if latest_update else 'none'}:"
        f"{latest_delete.isoformat() if latest_delete else 'none'}"
    )
