import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

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
        now = datetime.now(tz=timezone.utc)
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

    DELETE_ROW_FIELD_NAME = "delete-now"
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
            return False, {"row": "header", "error": "CSV file is empty or has no headers"}

        missing_headers = set(required_fields) - set(csv_reader.fieldnames)
        if missing_headers:
            return False, {"row": "header", "error": f"Missing required columns: {', '.join(missing_headers)}"}
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
            row_num = 0  # Will be incremented to 1 for first data row
            seen_combinations = set()

            for row in csv_reader:
                row_num += 1  # First data row is Row 1
                # Call model-specific validation hook
                row_errors, processed_data = self.validate_csv_row_data(row, row_num, seen_combinations)

                if row_errors:
                    # Format row data for display
                    row_display = self._format_row_for_display_from_raw(row)
                    for error in row_errors:
                        errors.append({"row": row_num, "error": error, "row_display": row_display})
                else:
                    # Use serializer if available
                    serializer_class = self.get_csv_import_serializer()
                    if serializer_class:
                        try:
                            # Extract non-serializer fields (like DELETE_ROW_FIELD_NAME) before validation
                            # These fields are not in the serializer schema but need to be preserved
                            non_serializer_fields = {}
                            # Check for delete field - look for both "delete" (set by validate_csv_row_data)
                            # and DELETE_ROW_FIELD_NAME ("delete-now" from CSV)
                            delete_key = None
                            delete_value = False
                            # First check for "delete" key (set by validate_csv_row_data in choices/admin.py)
                            if "delete" in processed_data:
                                delete_key = "delete"
                                delete_value = processed_data.get("delete", False)
                            else:
                                # Fallback: check for DELETE_ROW_FIELD_NAME
                                delete_key = next(
                                    (
                                        k
                                        for k in processed_data.keys()
                                        if k.strip().lower() == self.DELETE_ROW_FIELD_NAME
                                    ),
                                    None,
                                )
                                delete_value = processed_data.get(delete_key, False) if delete_key else False
                            # Always include delete field (even if False) so it's available in process_csv_row
                            # Store as "delete" for consistency in process_csv_row
                            non_serializer_fields["delete"] = delete_value
                            # Remove delete field from processed_data before serializer validation
                            if delete_key:
                                processed_data = {
                                    k: v
                                    for k, v in processed_data.items()
                                    if k != delete_key and k.strip().lower() != self.DELETE_ROW_FIELD_NAME
                                }

                            serializer = serializer_class(data=processed_data)
                            if serializer.is_valid():
                                # Merge serializer validated data with non-serializer fields
                                final_data = {**serializer.validated_data, **non_serializer_fields}
                                # Store row number with validated data
                                validated_data.append({"row_num": row_num, "data": final_data})
                            else:
                                # Format row data for display
                                row_display = self._format_row_for_display(processed_data)
                                for field, field_errors in serializer.errors.items():
                                    for error in field_errors:
                                        # Make error messages more user-friendly
                                        if (
                                            "A valid integer is required" in str(error)
                                            or "invalid" in str(error).lower()
                                        ):
                                            errors.append(
                                                {
                                                    "row": row_num,
                                                    "error": (
                                                        f"'{field}' field has an invalid value. "
                                                        "Please check that numeric fields contain only numbers."
                                                    ),
                                                    "row_display": row_display,
                                                }
                                            )
                                        else:
                                            errors.append(
                                                {
                                                    "row": row_num,
                                                    "error": f"{field}: {error}",
                                                    "row_display": row_display,
                                                }
                                            )
                        except (ValueError, TypeError) as e:
                            # Catch any conversion errors during serializer initialization/validation
                            error_msg = str(e)
                            # Format row data for display
                            row_display = self._format_row_for_display(processed_data)
                            if "invalid literal for int()" in error_msg or "invalid" in error_msg.lower():
                                errors.append(
                                    {
                                        "row": row_num,
                                        "error": (
                                            "Invalid value found in row. Please check that all numeric fields "
                                            "(like 'ordernum') contain only numbers, and boolean fields contain "
                                            "true/false values."
                                        ),
                                        "row_display": row_display,
                                    }
                                )
                            else:
                                errors.append(
                                    {
                                        "row": row_num,
                                        "error": f"Error validating row data: {error_msg}",
                                        "row_display": row_display,
                                    }
                                )
                    else:
                        # Store row number with validated data
                        validated_data.append({"row_num": row_num, "data": processed_data})

        except ValueError as e:
            # Handle value conversion errors with more helpful messages
            error_msg = str(e)
            if "invalid literal for int()" in error_msg:
                # Extract the problematic value from the error message

                match = re.search(r"invalid literal for int\(\) with base 10: '([^']+)'", error_msg)
                if match:
                    bad_value = match.group(1)
                    errors.append(
                        {
                            "row": "CSV file",
                            "error": (
                                f"Invalid integer value '{bad_value}' found in CSV. "
                                "Please check numeric fields like 'ordernum' contain only numbers."
                            ),
                        }
                    )
                else:
                    errors.append({"row": "CSV file", "error": f"Invalid number format in CSV: {error_msg}"})
            else:
                errors.append({"row": "CSV file", "error": f"Invalid value in CSV: {error_msg}"})
            return False, errors, validated_data
        except Exception as e:
            logger.exception(f"Error validating CSV: {e}")
            errors.append(
                {
                    "row": "CSV file",
                    "error": (
                        f"Error reading CSV file: {str(e)}. "
                        "Please check that your CSV file is properly formatted and all required columns are present."
                    ),
                }
            )
            return False, errors, validated_data

        is_valid = len(errors) == 0
        return is_valid, errors, validated_data

    def get_csv_import_serializer(self):
        """
        Hook to provide a serializer for validation.
        Override in subclass to return a serializer class.
        """
        return None

    def _format_row_for_display(self, data):
        """
        Format row data for display in success/error message.
        Returns a comma-separated string of key fields (model, field, value, display).
        Values are escaped for safe HTML display.

        Args:
            data: Dictionary of validated row data

        Returns:
            str: Formatted row display string (HTML-escaped)
        """
        # Get key fields in order: model, field, value, display
        fields = ["model", "field", "value", "display"]
        values = []
        for field in fields:
            if field in data:
                field_value = data[field]
                if field_value is not None:
                    value_str = str(field_value).strip()
                    if value_str:  # Only add non-empty values
                        values.append(escape(value_str))
        return ", ".join(values)

    def _format_row_for_display_from_raw(self, row):
        """
        Format raw CSV row data for display in error message.
        Returns a comma-separated string of key fields (model, field, value, display).
        Values are escaped for safe HTML display.

        Args:
            row: Dictionary of raw CSV row data

        Returns:
            str: Formatted row display string (HTML-escaped)
        """
        # Get key fields in order: model, field, value, display
        fields = ["model", "field", "value", "display"]
        values = []
        for field in fields:
            if field in row:
                field_value = row[field]
                if field_value is not None:
                    try:
                        value_str = str(field_value).strip()
                        if value_str:  # Only add non-empty values
                            values.append(escape(value_str))
                    except (AttributeError, TypeError):
                        # Skip if we can't convert to string or strip
                        pass
        return ", ".join(values)

    def _format_import_error_message(self, errors):
        """
        Format error messages with row data grouped by row, similar to success message format.
        Returns HTML-formatted message for Django admin display.

        Args:
            errors: List of error dicts with 'row', 'error', and optionally 'row_display' keys

        Returns:
            str: HTML-formatted error message
        """

        message_parts = ["CSV validation failed. Please fix the following errors:"]

        # Group errors by row
        errors_by_row = {}
        header_errors = []
        csv_file_errors = []

        for error in errors:
            row_label = error["row"]
            if row_label == "header":
                header_errors.append(error["error"])
            elif row_label == "CSV file":
                csv_file_errors.append(error["error"])
            else:
                # Group by row number
                if row_label not in errors_by_row:
                    errors_by_row[row_label] = {
                        "row_display": error.get("row_display", ""),
                        "errors": [],
                    }
                errors_by_row[row_label]["errors"].append(error["error"])

        # Add header errors first
        for error_msg in header_errors:
            message_parts.append(f"Header row: {escape(error_msg)}")

        # Add CSV file errors
        for error_msg in csv_file_errors:
            message_parts.append(escape(error_msg))

        # Add row errors grouped by row
        if errors_by_row:
            # Sort by row number
            sorted_rows = sorted(errors_by_row.keys(), key=lambda x: x if isinstance(x, int) else 999)
            for row_num in sorted_rows:
                row_info = errors_by_row[row_num]
                row_display = row_info["row_display"]
                row_errors = row_info["errors"]

                # Show row data once, then list all errors
                if row_display:
                    message_parts.append(f"Row {row_num}: {row_display}")
                else:
                    message_parts.append(f"Row {row_num}:")

                # List all errors for this row
                for error_msg in row_errors:
                    message_parts.append(f"  - {escape(error_msg)}")

        # Join with <br> tags for HTML display
        html_message = "<br>".join(message_parts)
        return mark_safe(html_message)

    def _format_import_success_message(self, added_rows, updated_rows, deleted_rows):
        """
        Format a formalized success message with sections for added/updated/deleted rows.
        Returns HTML-formatted message for Django admin display.
        All user data is escaped for safe HTML display.

        Args:
            added_rows: List of dicts with 'row_num' and 'display' keys
            updated_rows: List of dicts with 'row_num' and 'display' keys
            deleted_rows: List of dicts with 'row_num' and 'display' keys

        Returns:
            str: HTML-formatted success message
        """

        message_parts = []

        if added_rows:
            message_parts.append("The following choices were added:")
            for row_info in added_rows:
                # row_info['display'] is already escaped from _format_row_for_display()
                message_parts.append(f"Row {row_info['row_num']}: {row_info['display']}")

        if updated_rows:
            if message_parts:
                message_parts.append("")  # Blank line between sections
            message_parts.append("The following choices were updated:")
            for row_info in updated_rows:
                # row_info['display'] is already escaped from _format_row_for_display()
                message_parts.append(f"Row {row_info['row_num']}: {row_info['display']}")

        if deleted_rows:
            if message_parts:
                message_parts.append("")  # Blank line between sections
            message_parts.append("The following choices were deleted:")
            for row_info in deleted_rows:
                # row_info['display'] is already escaped from _format_row_for_display()
                message_parts.append(f"Row {row_info['row_num']}: {row_info['display']}")

        if not message_parts:
            message_parts.append(f"No {self.model._meta.verbose_name_plural} were processed")

        # Join with <br> tags for HTML display
        html_message = "<br>".join(message_parts)
        return mark_safe(html_message)

    def process_csv_row(self, data):
        """
        Process and save a single CSV row.
        Override for custom logic. Default implementation uses get_or_create based on csv_unique_fields.

        Args:
            data: Validated data dict for the row

        Returns:
            tuple: (instance, created: bool, deleted: bool)
        """
        # Check if this row should be deleted
        # The delete flag may be stored as "delete" (after conversion from "delete-now")
        # or as DELETE_ROW_FIELD_NAME if it came through a different path
        should_delete = data.get("delete", False)
        if not should_delete:
            # Fallback: check for DELETE_ROW_FIELD_NAME and parse if it's a string
            delete_now_value = data.get(self.DELETE_ROW_FIELD_NAME, False)
            if isinstance(delete_now_value, str):
                # Import parse_bool if needed - but this should rarely be needed
                # since validate_csv_row_data should convert delete-now to delete
                from utils.json import parse_bool

                should_delete = parse_bool(delete_now_value)
            else:
                should_delete = bool(delete_now_value)
        # Filter out both "delete" and DELETE_ROW_FIELD_NAME from data_for_save
        data_for_save = {k: v for k, v in data.items() if k != "delete" and k != self.DELETE_ROW_FIELD_NAME}

        unique_fields = getattr(self, "csv_unique_fields", [])
        if unique_fields:
            lookup = {field: data_for_save[field] for field in unique_fields if field in data_for_save}

            # Try to find existing instance
            try:
                instance = self.model.objects.get(**lookup)
                if should_delete:
                    # Delete the instance (use soft delete if available)
                    if hasattr(instance, "disable"):
                        instance.disable()
                    else:
                        instance.delete()

                    return None, False, True
                else:
                    # Update existing instance
                    for key, value in data_for_save.items():
                        setattr(instance, key, value)
                    instance.save()
                    return instance, False, False
            except self.model.DoesNotExist:
                if should_delete:
                    # Row marked for delete but doesn't exist - skip silently
                    return None, False, False
                # Create new instance
                instance = self.model.objects.create(**data_for_save)
                return instance, True, False
        else:
            if should_delete:
                # Without unique fields, we can't identify what to delete
                logger.warning("Cannot delete row: csv_unique_fields not defined")
                return None, False, False
            instance = self.model.objects.create(**data_for_save)
            return instance, True, False

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
            error_message = self._format_import_error_message(errors)
            return False, error_message

        try:
            with transaction.atomic():
                added_rows = []
                updated_rows = []
                deleted_rows = []

                for row_info in validated_data:
                    row_num = row_info["row_num"]
                    data = row_info["data"]
                    instance, created, deleted = self.process_csv_row(data)

                    # Format row data for display (model, field, value, display)
                    row_display = self._format_row_for_display(data)

                    if deleted:
                        deleted_rows.append({"row_num": row_num, "display": row_display})
                    elif created:
                        added_rows.append({"row_num": row_num, "display": row_display})
                    else:
                        updated_rows.append({"row_num": row_num, "display": row_display})

                # Build formalized success message
                message = self._format_import_success_message(added_rows, updated_rows, deleted_rows)
                return True, message

        except Exception as e:
            logger.exception(f"Error importing CSV: {e}")
            return False, f"Error importing data: {escape(str(e))}"

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
