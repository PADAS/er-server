import csv
import logging
import re
import urllib.parse as urlparse
from functools import partial
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import model_ngettext
from django.forms import modelformset_factory
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

import choices.models as models
from choices.forms import ChoiceForm, ChoiceFormSet, CSVImportForm
from choices.serializers import ChoiceSerializer
from core.admin import BaseModelAdminMixin, ModelAdminDisplayingManyToManyFieldMixin
from utils.admin import CSVImportMixin, ExportDataActionMixin
from utils.json import parse_bool

logger = logging.getLogger(__name__)


@admin.register(models.Choice)
class ChoiceAdmin(CSVImportMixin, ModelAdminDisplayingManyToManyFieldMixin, ExportDataActionMixin):
    change_list_template = "admin/disable_change_list.html"
    delete_confirmation_template = "admin/soft_delete_confirmation.html"
    delete_selected_confirmation_template = "admin/soft_delete_selected_confirmation.html"

    form = ChoiceForm
    actions = ("disable_choices", "export_data_as_csv")
    ordering = ("model", "field", "value", "display", "ordernum", "is_active")
    list_display = ("model", "field", "value", "display", "ordernum", "_icon_display", "is_active")
    list_display_links = ("model", "field")
    search_fields = ("model", "field", "value", "display")
    list_filter = ("model", "field")
    list_editable = ("value", "display", "ordernum")
    exclude = ("delete_on", "is_active")

    # Fields used for both CSV export and import (except sub_choice_of which is export-only)
    # Note: model, field, value are required for import; others are optional
    fields_to_export = [
        "model",
        "field",
        "value",
        "display",
        "icon",
        "ordernum",
        "sub_choice_of",  # Export only - ManyToMany field not supported in CSV import
        "is_active",
        "delete-now",  # Import only - optional column to mark rows for deletion (obscured name)
    ]

    # CSV Import configuration
    # Note: display is optional and can be empty/blank
    csv_required_fields = ["model", "field", "value"]
    csv_unique_fields = ["model", "field", "value"]  # Fields that uniquely identify a record
    csv_excluded_import_fields = [
        "sub_choice_of",
        "delete-now",
    ]  # ManyToMany field and delete-now (hidden feature) - not in template
    csv_import_form_class = CSVImportForm
    csv_import_template = "admin/choices/import_csv.html"

    def get_changelist_formset(self, request, **kwargs):
        """Override to use custom formset for list_editable validation"""
        if request.method == "POST":
            defaults = {
                "formfield_callback": partial(self.formfield_for_dbfield, request=request),
                **kwargs,
            }
            return modelformset_factory(
                self.model,
                self.get_changelist_form(request),
                formset=ChoiceFormSet,
                extra=0,
                fields=self.list_editable,
                **defaults,
            )
        return super().get_changelist_formset(request, **kwargs)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.filter_active_choices()
        if not self.has_change_permission(request):
            queryset = queryset.none()
        return queryset

    def get_changeform_initial_data(self, request):
        if request.GET:
            return {"model": request.GET.get("model"), "field": request.GET.get("field")}
        super().get_changeform_initial_data(request)

    def pass_params_to_url(self, redirect_url, params):
        url_parts = list(urlparse.urlparse(redirect_url))
        url_parts[4] = urlencode(params)
        return urlparse.urlunparse(url_parts)

    def addvalue(self, request, obj, opts, action, url):
        self.message_user(
            request,
            _(
                'The {name} "{obj}" was {action} successfully. You may add another {name} below.'.format(
                    name=opts.verbose_name, obj=str(obj), action=action
                )
            ),
            messages.SUCCESS,
        )

        preserved_filters = self.get_preserved_filters(request)
        redirect_url = add_preserved_filters({"preserved_filters": preserved_filters, "opts": opts}, url)

        params = {"model": obj.model, "field": obj.field}
        redirect_url = self.pass_params_to_url(redirect_url, params)
        return HttpResponseRedirect(redirect_url)

    def response_add(self, request, obj, post_url_continue=None):
        if "_addvalue" in request.POST:
            opts = obj._meta
            return self.addvalue(request, obj, opts, "added", request.path)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_addvalue" in request.POST:
            opts = self.model._meta
            redirect_url = reverse(
                "admin:%s_%s_add" % (opts.app_label, opts.model_name), current_app=self.admin_site.name
            )
            return self.addvalue(request, obj, opts, "changed", redirect_url)
        return super().response_change(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        if "disable_choices" in request.POST:
            opts = self.model._meta
            self.message_user(
                request,
                _('The {name} "{object}" was disabled.'.format(name=opts.verbose_name, object=obj_display)),
                messages.WARNING,
            )

            if self.has_change_permission(request, None):
                post_url = reverse(
                    "admin:%s_%s_changelist" % (opts.app_label, opts.model_name), current_app=self.admin_site.name
                )
                preserved_filters = self.get_preserved_filters(request)
                post_url = add_preserved_filters({"preserved_filters": preserved_filters, "opts": opts}, post_url)

                return HttpResponseRedirect(post_url)
            else:
                post_url = reverse("admin:index", current_app=self.admin_site.name)
                return HttpResponseRedirect(post_url)
        return super().response_delete(request, obj_display, obj_id)

    def delete_disable_selected(self, modeladmin, request, queryset):
        delete = queryset.delete
        count = queryset.count
        modeladmin.message_user

        def _delete_closure():
            """
            Wraps the original delete method which gets called by
            delete_selected()
            """
            if "disable_choices" in request.POST:
                fmt = "Successfully disabled {0} {1}."
                messages.add_message(request, messages.WARNING, fmt.format(len(queryset), self.opts.verbose_name))
                result = queryset.soft_delete()
            else:
                fmt = _("Successfully deleted {count} {items}s.")
                messages.add_message(
                    request, messages.SUCCESS, fmt.format(count=count(), items=model_ngettext(modeladmin.opts, count()))
                )
                result = delete()

            return result

        def _message(request, message, message_level):
            pass

        queryset.delete = _delete_closure
        modeladmin.message_user = _message
        return delete_selected(modeladmin, request, queryset)

    def get_actions(self, request):
        """Patch delete_selected to have our method running"""
        actions = super().get_actions(request)
        actions["delete_selected"] = (
            self.delete_disable_selected,
            "delete_selected",
            delete_selected.short_description,
        )
        return actions

    def delete_model(self, request, obj):
        if "disable_choices" in request.POST:
            return obj.disable()

        super().delete_model(request, obj)

    def disable_choices(self, request, queryset):
        fmt = "Successfully disabled {0} {1}."
        self.message_user(request, fmt.format(len(queryset), self.opts.verbose_name), messages.WARNING)
        return queryset.disable_choices()

    disable_choices.short_description = "Disable selected choices"

    def _icon_display(self, obj):
        url = models.Choice.marker_icon(obj.icon_id)
        return mark_safe(f'<img src="{url}" style="height:2.5em; filter:opacity(0.8)" />')

    def export_data_as_csv(self, request, queryset):
        """Override to filter out non-model fields from export"""
        # Filter out fields that don't exist on the model (like 'delete-now'), and
        # exclude ManyToMany fields (like 'sub_choice_of') because Django's queryset.values()
        # does not support serializing ManyToMany fields and will raise an error if they are included.
        export_fields = [f for f in self.fields_to_export if f not in ["delete-now", "sub_choice_of"]]

        model = queryset.model
        now = timezone.now()
        download_filename = f'{model._meta.model_name}_data_{now.strftime("%Y-%m-%d")}.csv'

        response = HttpResponse(
            content_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={download_filename}"},
        )
        data = queryset.values(*export_fields)
        writer = csv.DictWriter(response, fieldnames=export_fields)
        writer.writeheader()
        writer.writerows(data)

        return response

    # CSV Import hooks - override CSVImportMixin methods for Choice-specific behavior

    def get_csv_import_serializer(self):
        """Return the serializer to use for validation"""
        return ChoiceSerializer

    def get_csv_example_row(self):
        """Provide example data for CSV template"""
        return {
            "model": "activity.event",
            "field": "priority",
            "value": "high",
            "display": "High Priority",  # Optional - can be empty/blank (will default to value if empty)
            "icon": "",
            "ordernum": "1",
            "is_active": "true",
        }

    def validate_csv_row_data(self, row, row_num, seen_combinations):
        """
        Choice-specific CSV row validation.
        Override from CSVImportMixin to add custom validation logic.
        """
        row_errors = []

        # Check if this is a delete operation (hidden feature - not advertised)
        # Look for "delete-now" column (obscured name)
        # Handle case-insensitive and whitespace-tolerant lookup
        delete_str = None
        for key in row.keys():
            if key.strip().lower() == "delete-now":
                delete_str = (row.get(key) or "").strip()
                break
        if delete_str is None:
            delete_str = (row.get("delete-now") or "").strip()
        should_delete = parse_bool(delete_str) if delete_str else False

        # If deleting, only require unique identifier fields
        if should_delete:
            required_fields = self.csv_unique_fields
        else:
            required_fields = self.csv_required_fields

        # Check required fields are not empty
        for field in required_fields:
            value = (row.get(field) or "").strip()
            if not value:
                row_errors.append(f"'{field}' is required and cannot be empty")

        # Note: display is optional and can be empty/blank - if not provided, it will default to value

        # Validate model is a valid choice
        model_value = (row.get("model") or "").strip()
        valid_models = [choice[0] for choice in models.Choice.MODEL_REF_CHOICES]
        if model_value and model_value not in valid_models:
            row_errors.append(
                f"'{model_value}' is not a valid model choice. " f"Valid choices are: {', '.join(valid_models)}"
            )

        # Check for duplicates within the CSV file (skip for delete operations)
        field_value = (row.get("field") or "").strip()
        value_value = (row.get("value") or "").strip()
        combination_key = (model_value, field_value, value_value)

        if not should_delete:
            # Validate field format: only unicode word characters (letters, numbers, underscores) allowed (no spaces)
            if field_value and not re.match(r"^\w+$", field_value):
                row_errors.append(
                    f"'field' must contain only letters, numbers, and underscores (no spaces). " f"Got: '{field_value}'"
                )
            # Validate value format: only unicode word characters (letters, numbers, underscores) allowed (no spaces)
            if value_value and not re.match(r"^\w+$", value_value):
                row_errors.append(
                    f"'value' must contain only letters, numbers, and underscores (no spaces). " f"Got: '{value_value}'"
                )

            # Only check for duplicates if not deleting
            if combination_key in seen_combinations:
                row_errors.append(
                    f"Duplicate entry: (model={model_value}, field={field_value}, "
                    f"value={value_value}) already exists in this CSV"
                )
            else:
                seen_combinations.add(combination_key)

        # Skip optional field validation if deleting
        ordernum_value = None
        if not should_delete:
            # Validate ordernum is an integer if provided
            ordernum_str = (row.get("ordernum") or "").strip()
            if ordernum_str:
                try:
                    ordernum_value = int(ordernum_str)
                except ValueError:
                    row_errors.append(f"'ordernum' must be an integer, got '{ordernum_str}'")

            # Validate is_active is a boolean if provided
            is_active_str = (row.get("is_active") or "").strip()
            is_active = True  # Default value
            if is_active_str:
                # Validate format before parsing
                valid_bool_strings = ["true", "1", "yes", "ok", "okay", "false", "0", "no", "n"]
                if is_active_str.lower() not in valid_bool_strings:
                    row_errors.append(
                        f"'is_active' must be a boolean value (true/false, 1/0, yes/no/ok), got '{is_active_str}'"
                    )
                else:
                    is_active = parse_bool(is_active_str)
        else:
            # For delete operations, is_active is always set to True in processed_data below.
            is_active = True

        # Prepare validated data (this format is expected by the mixin)
        # Only include fields that passed validation
        if should_delete:
            display_value = ""
            icon_value = None
        else:
            display_value = (row.get("display") or "").strip() or value_value
            icon_value = (row.get("icon") or "").strip() or None

        processed_data = {
            "model": model_value,
            "field": field_value,
            "value": value_value,
            "display": display_value,
            "icon": icon_value,
            "is_active": is_active if not should_delete else True,
            "delete": should_delete,
        }
        # Only add ordernum if it was successfully validated (or not provided)
        if ordernum_value is not None:
            processed_data["ordernum"] = ordernum_value
        elif not should_delete and not (row.get("ordernum") or "").strip():
            # Allow None/empty ordernum
            processed_data["ordernum"] = None

        return row_errors, processed_data

    def _format_row_for_display(self, data):
        """
        Format row data for display in success/error message.
        Includes model, field, value, display, and optionally is_active, ordernum, icon.

        Args:
            data: Dictionary of validated row data

        Returns:
            str: Formatted row display string
        """
        # Core fields always shown
        core_fields = ["model", "field", "value", "display"]
        values = []

        for field in core_fields:
            if field in data:
                field_value = data[field]
                if field_value is not None:
                    value_str = str(field_value).strip()
                    if value_str:  # Only add non-empty values
                        values.append(value_str)

        # Additional fields to show if they're set and meaningful
        additional_fields = ["is_active", "ordernum", "icon"]
        for field in additional_fields:
            if field in data:
                field_value = data[field]
                if field_value is not None:
                    if field == "is_active":
                        # Show is_active as true/false
                        values.append(f"is_active={str(field_value).lower()}")
                    elif field == "ordernum":
                        # Show ordernum if it's set
                        values.append(f"ordernum={field_value}")
                    elif field == "icon" and field_value:
                        # Show icon if it's not empty
                        values.append(f"icon={field_value}")

        return ", ".join(values)


@admin.register(models.DisableChoice)
class DisableChoiceAdmin(BaseModelAdminMixin):
    form = ChoiceForm
    # actions = ('disable_choices', )
    ordering = ("model", "field", "ordernum", "display", "delete_on")
    list_display = ("model", "field", "value", "display", "ordernum", "delete_on", "is_active")
    list_display_links = ("model", "field")
    search_fields = ("model", "field", "value", "display")
    list_editable = ("value", "display", "ordernum", "is_active")
    list_filter = ("value", "delete_on", "field")

    def get_changelist_formset(self, request, **kwargs):
        """Override to use custom formset for list_editable validation"""
        if request.method == "POST":
            defaults = {
                "formfield_callback": partial(self.formfield_for_dbfield, request=request),
                **kwargs,
            }
            return modelformset_factory(
                self.model,
                self.get_changelist_form(request),
                formset=ChoiceFormSet,
                extra=0,
                fields=self.list_editable,
                **defaults,
            )
        return super().get_changelist_formset(request, **kwargs)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.filter_inactive_choices()
        if not self.has_change_permission(request):
            queryset = queryset.none()
        return queryset

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if change and obj.is_active:
            obj.delete_on = None
        super().save_model(request, obj, form, change)


@admin.register(models.DynamicChoice)
class DynamicChoiceAdmin(BaseModelAdminMixin):
    ordering = ("id", "model_name")
    list_display = ("id", "model_name", "criteria")
    list_display_links = ("id",)
    search_fields = ("model_name",)
