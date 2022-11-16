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
    if qs.exists():
        if delete_revision:
            for row in qs:
                _raw_delete_revisions(qs.model, row.id)
        _raw_delete(qs)


def _raw_delete_revisions(model, object_id):
    return _raw_delete(model.revision.model.objects.filter(object_id=object_id))


def _raw_delete(qs):
    if qs.exists():
        qs._raw_delete(qs.db)
