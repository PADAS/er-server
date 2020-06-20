from django.utils.timezone import get_default_timezone_name
from django.contrib.admin.templatetags.admin_modify import *
from django.contrib.admin.templatetags.admin_modify import \
    submit_row as original_submit_row


def timezone_used():
    tz = get_default_timezone_name()
    return tz


TIMEZONE_USED = timezone_used()


@register.inclusion_tag('admin/choices_submit_line.html', takes_context=True)
def submit_row(context):
    ctx = original_submit_row(context)
    if ctx['opts'].model_name == 'gpxtrackfile':
        ctx['show_save_and_add_another'] = True

    if ctx['opts'].model_name == 'choice':
        ctx.update({'addchoices': True})
    return ctx
