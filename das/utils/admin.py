import csv
from typing import List
from urllib.parse import urlencode

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone


class DefaultFilterMixin:
    def get_default_filters(self, request):
        """Set default filters to the page.
        request (Request)
        Returns (dict):
            Default filter to encode.
        """
        raise NotImplementedError()

    def changelist_view(self, request, extra_context=None):
        ref = request.META.get("HTTP_REFERER", "")
        path = request.META.get("PATH_INFO", "")
        # If already have query parameters or if the page
        # was referred from it self (by drilldown or redirect)
        # don't apply default filter.
        if request.GET or ref.endswith(path):
            return super().changelist_view(request, extra_context=extra_context)
        query = urlencode(self.get_default_filters(request))
        return redirect("{}?{}".format(path, query))


class FieldSetElementMixin:
    def _remove_fields_from_fieldsets(
        self, fieldsets, field_to_remove: str, fieldset_index: int, field_index: int = 1
    ) -> tuple:
        fieldsets[fieldset_index][field_index]["fields"] = tuple(
            field for field in fieldsets[fieldset_index][field_index]["fields"] if not field in (field_to_remove,)
        )
        return fieldsets


class ExportDataActionMixin:
    queryset: QuerySet = None
    fields_to_export: List[str] = []

    @admin.action(description="Export selected items")
    def export_data_as_csv(self, request, queryset) -> HttpResponse:
        """Enable admin page to export current data as CSV file."""
        model = queryset.model
        now = timezone.now()
        download_filename = f'{model._meta.model_name}_data_{now.strftime("%Y-%m-%d")}.csv'

        response = HttpResponse(
            content_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={download_filename}"},
        )
        data = queryset.values(*self.fields_to_export)
        writer = csv.DictWriter(response, fieldnames=self.fields_to_export)
        writer.writeheader()
        writer.writerows(data)

        return response
