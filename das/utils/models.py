from typing import overload

from django_multitenant.mixins import TenantManagerMixin

from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.db.models import Manager, Max


def migrate_permissions(apps):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None


def update_all_contenttypes(**kwargs):
    try:
        from django.contrib.contenttypes.management import (
            update_contenttypes as create_contenttypes,
        )
    except ImportError:
        from django.contrib.contenttypes.management import create_contenttypes

    for app_config in apps.get_app_configs():
        create_contenttypes(app_config, verbosity=0, **kwargs)


def create_all_permissions(**kwargs):
    for app_config in apps.get_app_configs():
        create_permissions(app_config, verbosity=0, **kwargs)


@overload
def getattr_jsonfield(obj: object, name: str) -> object:
    """Extension to getattr, to describe a path into a django orm jsonfield.
    Supports the jsonfield query expression syntax for navigating a json field

    Args:
        obj (object): object to get attribute from
        name (str): name of attribute
    """
    ...


@overload
def getattr_jsonfield(obj: object, name: str, default: object) -> object:
    """Extension to getattr, to describe a path into a django orm jsonfield.
    Supports the jsonfield query expression syntax for navigating a json field

    Args:
        obj (object): object to get attribute from
        name (str): name of attribute
        default (object): if attribute is not found, return this
    """
    ...


def getattr_jsonfield(obj: object, name: str, *args) -> object:
    if len(args) > 1:
        raise TypeError(f"getattr_jsonfield expected at most 3 arguments, got {2 + len(args)}")

    is_default_set = len(args) == 1
    default = args[0] if args else None

    if "__" not in name:
        if is_default_set:
            return getattr(obj, name, default)
        return getattr(obj, name)

    path = name.split("__")

    attr_name = path.pop(0)
    try:
        obj = getattr(obj, attr_name)
    except AttributeError:
        if is_default_set:
            return default
        raise

    for attr_name in path:
        try:
            attr_id = int(attr_name)
        except ValueError:
            try:
                obj = obj[attr_name]
            except KeyError:
                if is_default_set:
                    return default
                raise
        else:
            try:
                obj = obj[attr_id]
            except IndexError:
                if is_default_set:
                    return default
                raise

    return obj


def get_next_int_val(app_label: str, model_name: str, column_name: str) -> int:
    model = apps.get_model(app_label, model_name)
    max_queryset = model.objects.annotate(Max(column_name))
    max_value = getattr(max_queryset[0], column_name) if max_queryset.exists() else 0

    return max_value + 1


class CommonTenantManager(TenantManagerMixin, Manager):
    """
    Generic Manager without special methods, just to use TenantManagerMixin
    """

    use_in_migrations = True
