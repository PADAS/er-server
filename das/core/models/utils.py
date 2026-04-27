"""
Utility functions for deleting data from models with revisions.
"""


def delete_data_from_qs(qs, delete_revision=False) -> None:
    """
    Delete data from a queryset with or without revisions.

    Args:
        qs (QuerySet): The queryset to delete data from.
        delete_revision (bool): Whether to delete revisions.

    Returns:
        None
    """
    if delete_revision:
        # Bulk-delete all revisions via a DB-side subquery — avoids loading IDs into memory.
        _raw_delete(qs.model.revision.model.objects.filter(object_id__in=qs.values("id")))
    _raw_delete(qs)


def _raw_delete(qs):
    qs._raw_delete(qs.db)
