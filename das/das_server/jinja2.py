from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse
from django.utils import timezone

from jinja2 import Environment


def environment(**options):
    '''
    Update the environment with custom functions so they'll be available within Jinja2 templates.

    For more information about why this is necessary, see this link:
    https://docs.djangoproject.com/en/2.1/topics/templates/#django.template.backends.jinja2.Jinja2

    :param options:
    :return:
    '''
    env = Environment(**options)
    env.globals.update({
        'static': staticfiles_storage.url,
        'url': reverse,
        'localtime': timezone.localtime,
    })
    return env
