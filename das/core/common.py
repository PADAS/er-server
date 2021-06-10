from django.utils.timezone import get_default_timezone_name
from django.contrib.admin.templatetags.admin_modify import *
from django.contrib.admin.templatetags.admin_modify import \
    submit_row as original_submit_row
from django.contrib.admin.sites import site as default_site
from django.contrib.admin import ModelAdmin
from django.conf import settings
from django.contrib import admin
from django import forms

from django.contrib.admin.utils import display_for_field, lookup_field
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.fields.related import ManyToManyRel
from django.template.defaultfilters import linebreaksbr
from django.utils.html import conditional_escape
from django import forms
from django.utils import formats, timezone


def timezone_used():
    tz = get_default_timezone_name()
    return tz


TIMEZONE_USED = timezone_used()


@register.inclusion_tag('admin/choices_submit_line.html', takes_context=True)
def submit_row(context):
    ctx = original_submit_row(context)
    if ctx['opts'].model_name == 'gpxtrackfile':
        ctx['show_popclose'] = True
        ctx['show_save_and_add_another'] = ctx['show_save']

    if ctx['opts'].model_name == 'choice':
        ctx.update({'addchoices': True})

    if ctx['opts'].model_name == 'refreshrecreateeventdetailview':
        ctx['show_save_and_continue'] = False
        ctx['show_save'] = False
        ctx['show_close'] = True
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


class AdminReadonlyField(admin.helpers.AdminReadonlyField):

    def display_form_field(self, field):
        form_fieldtype = self.form.fields.get(field)
        value = form_fieldtype.initial
        if isinstance(form_fieldtype, forms.SplitDateTimeField) and value:
            return formats.localize(timezone.template_localtime(value))
        return value if value else self.empty_value_display

    def contents(self):
        if self.model_admin.opts.model_name in ['patrolsegment', 'patrol']:
            from django.contrib.admin.templatetags.admin_list import _boolean_icon
            field, obj, model_admin = self.field['field'], self.form.instance, self.model_admin
            try:
                f, attr, value = lookup_field(field, obj, model_admin)
            except (AttributeError, ValueError, ObjectDoesNotExist):
                result_repr = self.display_form_field(field)
            else:
                if field in self.form.fields:
                    widget = self.form[field].field.widget
                    # This isn't elegant but suffices for contrib.auth's
                    # ReadOnlyPasswordHashWidget.
                    if getattr(widget, 'read_only', False):
                        return widget.render(field, value)
                if f is None:
                    if getattr(attr, 'boolean', False):
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
