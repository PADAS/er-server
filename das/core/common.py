from django.utils.timezone import get_default_timezone_name
from django.contrib.admin.templatetags.admin_modify import *
from django.contrib.admin.templatetags.admin_modify import \
    submit_row as original_submit_row
from django.contrib.admin.sites import site as default_site
from django.contrib.admin import ModelAdmin
from django.conf import settings
from datetime import datetime



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
    return ctx


def get_midnight_datetime():
    today = datetime.today()
    return datetime.combine(today, datetime.max.time())


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

