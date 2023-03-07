import uuid
from typing import Any

from django.apps.registry import Apps
from django.conf import settings
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def copy_model_column(
    app_label: str,
    model_name: str,
    source_column: str,
    target_column: str,
    apps: Apps,
    schema_editor: BaseDatabaseSchemaEditor,
) -> None:
    db_alias = schema_editor.connection.alias
    model = apps.get_model(app_label, model_name)

    for instance in model.objects.using(db_alias).all():
        source_value = getattr(instance, source_column)
        setattr(instance, target_column, source_value)
        instance.save()


def populate_model_uuid_column(
    app_label: str, model_name: str, column_name: str, apps: Apps, schema_editor: BaseDatabaseSchemaEditor
):
    db_alias = schema_editor.connection.alias
    model = apps.get_model(app_label, model_name)

    for instance in model.objects.using(db_alias).all():
        setattr(instance, column_name, uuid.uuid4())
        instance.save()


def set_column_value(
    app_label: str, model_name: str, column_name: str, value: Any, apps: Apps, schema_editor: BaseDatabaseSchemaEditor
):
    db_alias = schema_editor.connection.alias
    model = apps.get_model(app_label, model_name)

    for instance in model.objects.using(db_alias).all():
        setattr(instance, column_name, value)
        instance.save()


def copy_uuid_references(
    app_name, model_name, relationship_field, uuid_column, referrer_uuid_column, apps, schema_editor
):
    db_alias = schema_editor.connection.alias
    model = apps.get_model(app_name, model_name)

    for instance in model.objects.using(db_alias).all():
        propagate_uuid_reference(instance, relationship_field, uuid_column, referrer_uuid_column)


def propagate_uuid_reference(instance, relationship_field, uuid_column, referrer_uuid_column):
    instance_uuid = getattr(instance, uuid_column)

    for related_instance in getattr(instance, relationship_field).all():
        setattr(related_instance, referrer_uuid_column, instance_uuid)
        related_instance.save()


def default_tenant_id():
    from django_multitenant.utils import get_current_tenant

    from core.utils import DASTenantManagement

    tenant = get_current_tenant()
    if tenant:
        tenant_id = tenant.id
    else:
        das_tenant_management = DASTenantManagement(domain=settings.SERVER_FQDN)
        tenant_id = das_tenant_management.get_tenant_id()

    return tenant_id
