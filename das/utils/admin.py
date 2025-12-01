import csv
import io
import logging
from typing import List
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


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
            field for field in fieldsets[fieldset_index][field_index]["fields"] if field not in (field_to_remove,)
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


class CSVImportMixin:
    """
    Mixin for Django admin classes to enable CSV import functionality.

    Subclasses must define:
    - fields_to_export: List[str] - List of fields for import (and export)
    - csv_required_fields: List[str] - Fields that are required in CSV
    - csv_import_form_class: Form class for file upload (defaults to a basic form)
    - csv_import_template: str - Template path for the import page

    Subclasses can override:
    - validate_csv_row_data() - For model-specific validation
    - get_csv_import_serializer() - To provide a serializer for validation
    - process_csv_row() - For custom import logic per row
    """

    fields_to_export: List[str] = []
    csv_required_fields: List[str] = []
    csv_import_form_class = None
    csv_import_template: str = "admin/csv_import.html"

    def get_urls(self):
        """Add CSV import URL to admin URLs - must come before default URLs"""
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="%s_%s_import_csv" % info,
            ),
        ]
        urls = super().get_urls()
        return custom_urls + urls

    def _get_csv_field_info(self):
        """Get field information for CSV import based on fields_to_export"""
        # Filter out fields that shouldn't be imported (like ManyToMany fields)
        excluded_import_fields = getattr(self, "csv_excluded_import_fields", ["sub_choice_of"])
        optional_fields = [
            f for f in self.fields_to_export if f not in self.csv_required_fields and f not in excluded_import_fields
        ]
        all_fields = self.csv_required_fields + optional_fields
        return self.csv_required_fields, optional_fields, all_fields

    def _validate_csv_headers(self, csv_reader):
        """Validate CSV headers"""
        required_fields, optional_fields, all_fields = self._get_csv_field_info()

        if not csv_reader.fieldnames:
            return False, {"row": 0, "error": "CSV file is empty or has no headers"}

        missing_headers = set(required_fields) - set(csv_reader.fieldnames)
        if missing_headers:
            return False, {"row": 0, "error": f"Missing required columns: {', '.join(missing_headers)}"}
        return True, None

    def validate_csv_row_data(self, row, row_num, seen_combinations):
        """
        Hook for model-specific row validation.
        Override this in subclass for custom validation logic.

        Returns: (row_errors: list, processed_data: dict)
        """
        return [], row

    def validate_csv_data(self, csv_file):
        """
        Validate CSV data before import.

        Args:
            csv_file: File-like object containing CSV data

        Returns:
            tuple: (is_valid: bool, errors: list, validated_data: list)
        """
        errors = []
        validated_data = []

        try:
            csv_file.seek(0)
            content = csv_file.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8")

            csv_reader = csv.DictReader(io.StringIO(content))

            # Validate headers
            is_valid, error = self._validate_csv_headers(csv_reader)
            if not is_valid:
                errors.append(error)
                return False, errors, validated_data

            # Validate each row
            row_num = 1  # Start at 1 (header is row 0)
            seen_combinations = set()

            for row in csv_reader:
                row_num += 1
                # Call model-specific validation hook
                row_errors, processed_data = self.validate_csv_row_data(row, row_num, seen_combinations)

                if row_errors:
                    for error in row_errors:
                        errors.append({"row": row_num, "error": error})
                else:
                    # Use serializer if available
                    serializer_class = self.get_csv_import_serializer()
                    if serializer_class:
                        serializer = serializer_class(data=processed_data)
                        if serializer.is_valid():
                            validated_data.append(serializer.validated_data)
                        else:
                            for field, field_errors in serializer.errors.items():
                                for error in field_errors:
                                    errors.append({"row": row_num, "error": f"{field}: {error}"})
                    else:
                        validated_data.append(processed_data)

        except Exception as e:
            logger.exception(f"Error validating CSV: {e}")
            errors.append({"row": 0, "error": f"Error reading CSV file: {str(e)}"})
            return False, errors, validated_data

        is_valid = len(errors) == 0
        return is_valid, errors, validated_data

    def get_csv_import_serializer(self):
        """
        Hook to provide a serializer for validation.
        Override in subclass to return a serializer class.
        """
        return None

    def process_csv_row(self, data):
        """
        Process and save a single CSV row.
        Override for custom logic. Default implementation uses get_or_create based on csv_unique_fields.

        Args:
            data: Validated data dict for the row

        Returns:
            tuple: (instance, created: bool)
        """
        unique_fields = getattr(self, "csv_unique_fields", [])
        if unique_fields:
            lookup = {field: data[field] for field in unique_fields if field in data}
            instance, created = self.model.objects.update_or_create(defaults=data, **lookup)
            return instance, created
        else:
            instance = self.model.objects.create(**data)
            return instance, True

    def import_csv_data(self, csv_file):
        """
        Import data from CSV file after validation.

        Args:
            csv_file: File-like object containing CSV data

        Returns:
            tuple: (success: bool, message: str)
        """
        is_valid, errors, validated_data = self.validate_csv_data(csv_file)

        if not is_valid:
            error_message = "CSV validation failed. Please fix the following errors:\n"
            for error in errors:
                error_message += f"Row {error['row']}: {error['error']}\n"
            return False, error_message

        try:
            with transaction.atomic():
                created_count = 0
                updated_count = 0

                for data in validated_data:
                    instance, created = self.process_csv_row(data)
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                message = (
                    f"Successfully imported {created_count + updated_count} {self.model._meta.verbose_name_plural}: "
                    f"{created_count} created, {updated_count} updated"
                )
                return True, message

        except Exception as e:
            logger.exception(f"Error importing CSV: {e}")
            return False, f"Error importing data: {str(e)}"

    def _download_template_response(self):
        """Generate CSV template download response"""
        required_fields, optional_fields, all_fields = self._get_csv_field_info()

        response = HttpResponse(
            content_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={self.model._meta.model_name}_import_template.csv"},
        )

        writer = csv.writer(response)
        writer.writerow(all_fields)

        # Add an example row if get_csv_example_row is implemented
        if hasattr(self, "get_csv_example_row"):
            example_data = self.get_csv_example_row()
            example_row = [example_data.get(field, "") for field in all_fields]
            writer.writerow(example_row)

        return response

    def import_csv_view(self, request):
        """Admin view for importing CSV"""
        # Handle template download
        if request.GET.get("download_template"):
            return self._download_template_response()

        if request.method == "POST":
            form_class = self.csv_import_form_class or self._get_default_import_form()
            form = form_class(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]

                # Validate and import
                success, message = self.import_csv_data(csv_file)

                if success:
                    self.message_user(request, message, messages.SUCCESS)
                    return HttpResponseRedirect(
                        reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
                    )
                else:
                    self.message_user(request, message, messages.ERROR)
        else:
            form_class = self.csv_import_form_class or self._get_default_import_form()
            form = form_class()

        context = {
            "form": form,
            "title": f"Import {self.model._meta.verbose_name_plural} from CSV",
            "site_title": self.admin_site.site_title,
            "site_header": self.admin_site.site_header,
            "has_permission": True,
            "opts": self.model._meta,
        }

        return render(request, self.csv_import_template, context)

    def _get_default_import_form(self):
        """Create a basic CSV import form if none is provided"""
        from django import forms

        class DefaultCSVImportForm(forms.Form):
            csv_file = forms.FileField(
                label="CSV File",
                help_text="Upload a CSV file to import data",
                widget=forms.FileInput(attrs={"accept": ".csv"}),
            )

            def clean_csv_file(self):
                csv_file = self.cleaned_data.get("csv_file")
                if not csv_file:
                    raise forms.ValidationError("No file uploaded")
                if not csv_file.name.endswith(".csv"):
                    raise forms.ValidationError("File must be a CSV file (.csv)")
                if csv_file.size > 10 * 1024 * 1024:
                    raise forms.ValidationError("File size must be under 10MB")
                return csv_file

        return DefaultCSVImportForm
