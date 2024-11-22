import logging
import uuid
from argparse import FileType
from sys import stdin
from typing import Dict, List

from psycopg2.extras import Json

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import Model

from activity.models import Event, EventDetails, EventFile, EventNote
from revision.manager import get_revision_model
from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    logger = logging.getLogger(__name__)
    help = """Restore event(s) that have been deleted. Uses the event revisions to bring back a deleted event.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "pks",
            nargs="?",
            type=FileType("r"),
            default=stdin,
            help="list of pk event ids to restore, by file or stdin",
        )

    def handle(self, *args, **options):
        if not options["pks"]:
            raise ValueError("requires list of event ids")

        for pk in iter(options["pks"].readline, ""):
            if pk := pk.strip():
                with transaction.atomic():
                    restore_event(pk)


def restore_event(event_id: str) -> None:
    if Event.objects.filter(id=event_id).exists():
        logger.info("Event with id %s already exists, no restore performed", event_id)
        return
    event_revisions = get_revisions_for_object(Event, event_id)
    if not event_revisions:
        logger.info("Event with id %s was not found in revisions, no restore performed", event_id)

    the_revision = combine_revisions(event_revisions, event_id)
    the_revision["serial_number"] = get_next_serial_number(Event._meta.db_table)

    with connection.cursor() as cursor:
        sql = make_sql_insert_for_restoring_row(Event, the_revision)

        cursor.execute(sql, the_revision)
        remove_action_revision(Event, event_id)

        restore_event_child(cursor, EventNote, event_id)
        restore_event_child(cursor, EventDetails, event_id)
        restore_event_file(cursor, event_id)


def restore_event_file(cursor, event_id: str) -> None:
    restore_event_child(cursor, EventFile, event_id)
    for event_file in EventFile.objects.filter(event_id=event_id):
        usercontent_model = event_file.usercontent_type.model_class()
        usercontent_id = event_file.usercontent_id
        if usercontent_model.objects.filter(id=usercontent_id).exists():
            logger.info(
                "%s with id %s already exists for event with id %s", str(usercontent_model), usercontent_id, event_id
            )
            continue

        revisions = get_revisions_for_object(usercontent_model, usercontent_id)
        if not revisions:
            logger.info(
                "%s with id %s was not found in revisions, no restore performed", str(usercontent_model), usercontent_id
            )
            continue
        the_revision = combine_revisions(revisions, usercontent_id)

        sql = make_sql_insert_for_restoring_row(usercontent_model, the_revision)
        cursor.execute(sql, the_revision)
        remove_action_revision(usercontent_model, usercontent_id)


def combine_revisions(revisions: List[Dict], primary_key: uuid.UUID = None) -> dict:
    # now we combine the revisions from oldest to newest
    tenant_settings = get_tenant_settings()
    fix_id_fields = [
        "das_tenant",
        "event_type",
        "created_by_user",
        "reported_by_content_type",
        "reported_by",
        "event",
        "created_by",
        "usercontent_type",
    ]
    json_fields = ["attributes", "data"]

    the_revision = {}
    for revision in revisions:
        the_revision.update(revision["data"])

    for id_field in fix_id_fields:
        if id_field in the_revision:
            the_revision[f"{id_field}_id"] = the_revision.pop(id_field)
    for json_field in json_fields:
        if json_field in the_revision:
            the_revision[json_field] = Json(the_revision[json_field])

    if "das_tenant_id" not in the_revision:
        the_revision["das_tenant_id"] = tenant_settings.id

    if primary_key:
        the_revision["id"] = primary_key

    return the_revision


def make_sql_insert_for_restoring_row(model: Model, the_revision: dict) -> str:
    column_list = ", ".join(the_revision.keys())
    value_list = ", ".join([f"%({key})s" for key in the_revision.keys()])

    sql = f"""INSERT INTO {model._meta.db_table} ({column_list}) VALUES ({value_list})"""
    return sql


def restore_event_child(cursor, child_model: Model, event_id: uuid.UUID) -> None:

    for child_id in get_revision_object_ids_for_event(child_model, event_id):
        child_revisions = get_revisions_for_object(child_model, child_id)
        if not child_revisions:
            logger.info("%s with id %s was not found in revisions, no restore performed", str(child_model), child_id)
            continue

        the_revision = combine_revisions(child_revisions, child_id)

        sql = make_sql_insert_for_restoring_row(child_model, the_revision)
        cursor.execute(sql, the_revision)
        remove_action_revision(child_model, child_id)


def get_revisions_for_object(model: Model, object_id: uuid.UUID) -> list:
    revision_model = get_revision_model_class(model)

    return revision_model.objects.filter(object_id=object_id).exclude(action="deleted").order_by("sequence").values()


def remove_action_revision(model: Model, object_id: uuid.UUID, action: str = "deleted") -> None:
    revision_model = get_revision_model_class(model)

    revision_model.objects.get(object_id=object_id, action=action).delete()


def get_revision_object_ids_for_event(model: Model, event_id: uuid.UUID) -> List[uuid.UUID]:
    """Get the revision object_id for child models of Event.
    We look in the data for the "event" field.
    {"data": {"event": "388f7e49-8159-4d4b-93a9-7bfb5f00334b", ...}
    """
    revision_model = get_revision_model_class(model)
    data_rows = revision_model.objects.filter(data__event=str(event_id), action="added").values_list(
        "object_id", flat=True
    )
    return data_rows


def get_next_serial_number(table_name: str) -> int:
    tenant_settings = get_tenant_settings()
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT MAX(serial_number) FROM {table_name} WHERE das_tenant_id='{tenant_settings.id}'")
        result = cursor.fetchone()
        return (result[0] or 0) + 1


def get_revision_model_class(model: Model):
    revision_model = get_revision_model(model)
    return revision_model.model_class()
