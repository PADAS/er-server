from django import template
from django.conf import settings

register = template.Library()

vv = ''


@register.simple_tag()
def get_settings_value(name):
    return getattr(settings, name, "")
