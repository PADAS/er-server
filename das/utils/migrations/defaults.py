from django.core.serializers import base
from django.db.migrations.state import StateApps


def _get_model(apps: StateApps, model_identifier: str):
    try:
        return apps.get_model(model_identifier)
    except (LookupError, TypeError):
        raise base.DeserializationError("Invalid model identifier: '%s'" % model_identifier)


def get_default_subject_type(SubjectType):
    subject_type, _ = SubjectType.objects.get_or_create(
        value="unassigned",
        defaults={"display": "Unassigned"},
    )
    return subject_type.value


def get_subject_type_field(SubjectSubType):
    fields = {field.name: field for field in SubjectSubType._meta.local_fields}
    return fields.get("subject_type")
