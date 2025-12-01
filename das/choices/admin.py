import logging
import urllib.parse as urlparse
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import model_ngettext
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

import choices.models as models
from choices.forms import ChoiceForm, CSVImportForm
from choices.serializers import ChoiceSerializer
from core.admin import BaseModelAdminMixin, ModelAdminDisplayingManyToManyFieldMixin
from utils.admin import CSVImportMixin, ExportDataActionMixin

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
    ]

    # CSV Import configuration
    csv_required_fields = ["model", "field", "value"]
    csv_unique_fields = ["model", "field", "value"]  # Fields that uniquely identify a record
    csv_excluded_import_fields = ["sub_choice_of"]  # ManyToMany field - not supported in import
    csv_import_form_class = CSVImportForm
    csv_import_template = "admin/choices/import_csv.html"

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
            "display": "High Priority",
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

        # Check required fields are not empty
        for field in self.csv_required_fields:
            value = row.get(field, "").strip()
            if not value:
                row_errors.append(f"'{field}' is required and cannot be empty")

        # Validate model is a valid choice
        model_value = row.get("model", "").strip()
        valid_models = [choice[0] for choice in models.Choice.MODEL_REF_CHOICES]
        if model_value and model_value not in valid_models:
            row_errors.append(
                f"'{model_value}' is not a valid model choice. " f"Valid choices are: {', '.join(valid_models)}"
            )

        # Check for duplicates within the CSV file
        field_value = row.get("field", "").strip()
        value_value = row.get("value", "").strip()
        combination_key = (model_value, field_value, value_value)

        if combination_key in seen_combinations:
            row_errors.append(
                f"Duplicate entry: (model={model_value}, field={field_value}, "
                f"value={value_value}) already exists in this CSV"
            )
        else:
            seen_combinations.add(combination_key)

        # Validate ordernum is an integer if provided
        ordernum = row.get("ordernum", "").strip()
        if ordernum:
            try:
                ordernum = int(ordernum)
            except ValueError:
                row_errors.append(f"'ordernum' must be an integer, got '{ordernum}'")

        # Validate is_active is a boolean if provided
        is_active_str = row.get("is_active", "").strip()
        is_active = True  # Default value
        if is_active_str:
            is_active_lower = is_active_str.lower()
            if is_active_lower in ["true", "1", "yes", "y"]:
                is_active = True
            elif is_active_lower in ["false", "0", "no", "n"]:
                is_active = False
            else:
                row_errors.append(
                    f"'is_active' must be a boolean value (true/false, 1/0, yes/no), got '{is_active_str}'"
                )

        # Prepare validated data (this format is expected by the mixin)
        processed_data = {
            "model": model_value,
            "field": field_value,
            "value": value_value,
            "display": row.get("display", "").strip() or value_value,
            "icon": row.get("icon", "").strip() or None,
            "ordernum": int(ordernum) if ordernum else None,
            "is_active": is_active,
        }

        return row_errors, processed_data


@admin.register(models.DisableChoice)
class DisableChoiceAdmin(BaseModelAdminMixin):
    # actions = ('disable_choices', )
    ordering = ("model", "field", "ordernum", "display", "delete_on")
    list_display = ("model", "field", "value", "display", "ordernum", "delete_on", "is_active")
    list_display_links = ("model", "field")
    search_fields = ("model", "field", "value", "display")
    list_editable = ("value", "display", "ordernum", "is_active")
    list_filter = ("value", "delete_on", "field")

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
