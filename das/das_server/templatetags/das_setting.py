from django import template
from django.conf import settings
from core.utils import get_site_name

register = template.Library()


@register.simple_tag()
def get_settings_value(name):
    return getattr(settings, name, "")


@register.simple_tag()
def retrieve_site_name():
    return get_site_name()
