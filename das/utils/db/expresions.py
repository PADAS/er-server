"""
Django expressions for database queries.
"""

from django.contrib.postgres.fields import ArrayField
from django.db.models import Subquery
from django.utils.functional import cached_property


class ArraySubquery(Subquery):
    """Supports using a subquery as an array in a query.

    Copied from Django 5.0.2 source code.
    """

    template = "ARRAY(%(subquery)s)"

    def __init__(self, queryset, **kwargs):
        super().__init__(queryset, **kwargs)

    @cached_property
    def output_field(self):
        return ArrayField(self.query.output_field)
