from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.contrib.admin.sites import site as default_site
from django.contrib.admin.templatetags.admin_modify import *
from django.contrib.admin.templatetags.admin_modify import (
    submit_row as original_submit_row,
)
from django.contrib.admin.utils import display_for_field, lookup_field
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.fields.related import ManyToManyRel
from django.template.defaultfilters import linebreaksbr
from django.utils import formats, timezone
from django.utils.html import conditional_escape
from django.utils.timezone import get_default_timezone_name


def timezone_used():
    tz = get_default_timezone_name()
    return tz


TIMEZONE_USED = timezone_used()


@register.inclusion_tag("admin/choices_submit_line.html", takes_context=True)
def submit_row(context):
    ctx = original_submit_row(context)
    if ctx["opts"].model_name == "gpxtrackfile":
        ctx["show_popclose"] = True
        ctx["show_save_and_add_another"] = ctx["show_save"]

    if ctx["opts"].model_name == "choice":
        ctx.update({"addchoices": True})

    if ctx["opts"].model_name == "refreshrecreateeventdetailview":
        ctx["show_save_and_continue"] = False
        ctx["show_save"] = False
        ctx["show_close"] = True
    return ctx


class AdminFeatureFlag:

    def __init__(self, model, flag):
        self.model = model
        self.flag = flag

    def __call__(self, admin_class):
        if not self.model:
            raise ValueError("A model must be passed to flag.")

        if not issubclass(admin_class, ModelAdmin):
            raise ValueError("Wrapped class must be subclass of ModelAdmin.")

        admin_site = default_site
        flag_status = getattr(settings, self.flag, False)

        if not flag_status:
            admin_site.unregister(self.model)
        else:
            return admin_class


class PreviewFeatureAdminMixin:
    """Hides a ModelAdmin from a tenant when its preview feature is off.

    Subclasses set ``preview_feature`` to the name of an entry in
    ``PREVIEW_FEATURES`` (e.g. ``"community_input_admin_enabled"``). The feature
    is resolved per request via ``get_preview_feature``, so it honours the
    feature's ``global_override`` — set that to ``True`` to expose the admin for
    every tenant at once. This is the sole gate for the admin; no
    Django-settings kill switch is needed in front of it.

    See ``utils/tenant/preview_features.py`` for the ``PREVIEW_FEATURES`` registry.
    """

    preview_feature: str = ""

    def _preview_feature_on(self) -> bool:
        from utils.tenant.preview_features import get_preview_feature

        if not self.preview_feature:
            return False
        return bool(get_preview_feature(self.preview_feature))

    def has_module_permission(self, request):
        return self._preview_feature_on() and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._preview_feature_on() and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self._preview_feature_on() and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self._preview_feature_on() and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._preview_feature_on() and super().has_delete_permission(request, obj)


class AdminReadonlyField(admin.helpers.AdminReadonlyField):

    def display_form_field(self, field):
        form_fieldtype = self.form.fields.get(field)
        value = form_fieldtype.initial
        if isinstance(form_fieldtype, forms.SplitDateTimeField) and value:
            return formats.localize(timezone.template_localtime(value))
        return value if value else self.empty_value_display

    def contents(self):
        if self.model_admin.opts.model_name in ["patrolsegment", "patrol"]:
            from django.contrib.admin.templatetags.admin_list import _boolean_icon

            field, obj, model_admin = self.field["field"], self.form.instance, self.model_admin
            try:
                f, attr, value = lookup_field(field, obj, model_admin)
            except (AttributeError, ValueError, ObjectDoesNotExist):
                result_repr = self.display_form_field(field)
            else:
                if field in self.form.fields:
                    widget = self.form[field].field.widget
                    # This isn't elegant but suffices for contrib.auth's
                    # ReadOnlyPasswordHashWidget.
                    if getattr(widget, "read_only", False):
                        return widget.render(field, value)
                if f is None:
                    if getattr(attr, "boolean", False):
                        result_repr = _boolean_icon(value)
                    else:
                        if hasattr(value, "__html__"):
                            result_repr = value
                        else:
                            result_repr = linebreaksbr(value)
                else:
                    if isinstance(f.remote_field, ManyToManyRel) and value is not None:
                        result_repr = ", ".join(map(str, value.all()))
                    else:
                        result_repr = display_for_field(value, f, self.empty_value_display)
                    result_repr = linebreaksbr(result_repr)
            return conditional_escape(result_repr)
        else:
            return super(AdminReadonlyField, self).contents()


admin.helpers.AdminReadonlyField = AdminReadonlyField
