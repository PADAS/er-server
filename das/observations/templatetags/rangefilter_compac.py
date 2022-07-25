
import django
from django import template

register = template.Library()

if django.VERSION[:2] >= (1, 10):
    from django.templatetags.static import static as _static
else:
    from django.contrib.admin import static as _static


@register.simple_tag()
def static(path):
    return _static(path)
