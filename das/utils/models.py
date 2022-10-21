import django
from django.contrib.auth.management import create_permissions


def migrate_permissions(apps):
    version = django.VERSION
    if version[0] > 1 or (version[0] == 1 and django.VERSION[1] > 9):
        for app_config in apps.get_app_configs():
            app_config.models_module = True
            create_permissions(app_config, apps=apps, verbosity=0)
            app_config.models_module = None
    else:
        apps.models_module = True
        create_permissions(apps, verbosity=0)
        apps.models_module = None


def update_all_contenttypes(**kwargs):
    from django.apps import apps
    try:
        from django.contrib.contenttypes.management import update_contenttypes as create_contenttypes
    except ImportError:
        from django.contrib.contenttypes.management import create_contenttypes

    for app_config in apps.get_app_configs():
        create_contenttypes(app_config, verbosity=0, **kwargs)


def create_all_permissions(**kwargs):
    from django.contrib.auth.management import create_permissions
    from django.apps import apps

    for app_config in apps.get_app_configs():
        create_permissions(app_config, verbosity=0, **kwargs)