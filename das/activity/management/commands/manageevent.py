import logging
import copy
import csv
from uuid import UUID
import os

import pandas as pd
from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction, connection
from django.db.models import Count
from django.contrib.contenttypes.models import ContentType

from activity.models import EventType, Event, EventDetails, EventCategory
from observations.models import SubjectType, SubjectSubType
import utils.schema_utils as schema_utils
import choices.models as choices
from utils import json
from utils.memoize import memoize

logger = logging.getLogger(__name__)


class ChoiceException(Exception):
    pass


class ChoiceNotFoundException(ChoiceException):
    pass


"""
there are some choice tables that map to existing Choices
in this scenario, if the id's don't match we need to remember
and match them manually
"""
CHOICE_MAPPING = {}


def add_to_choice_mapping(from_id, from_name, to_choice_id):
    if isinstance(from_id, str):
        from_id = UUID(str)
    CHOICE_MAPPING[str(from_id)] = dict(choice_id=to_choice_id, name=from_name)


def dump_choice_mapping(filepath):
    with open(filepath, mode="w") as fh:
        fh.write(json.dumps(CHOICE_MAPPING))


@memoize
def lookup_choice_value_by_id(table_row_id):
    # normalize uuid
    if isinstance(table_row_id, str):
        table_row_id = UUID(str)
    table_row_id = str(table_row_id)

    if table_row_id in CHOICE_MAPPING:
        table_row_id = CHOICE_MAPPING[table_row_id]['choice_id']

    choice_row = choices.Choice.objects.get(id=table_row_id)
    return choice_row.value


class Command(BaseCommand):
    help = 'Event Type managment commands'
    dry_run = False

    SUB_COMMANDS = ('dumptypes', 'deleteunusedtypes',
                    'migratetypes', 'dumplocalize', 'loadlocalize')
    PREVIOUS_EVENT_FIELD = 'previous_value'
    PREVIOUS_PROPERTY_FIELD = 'previous_property_name'
    CURRENT_PROPERTY_NAME = 'property_name'
    CURRENT_PROPERTY_VALUE = 'property_value'
    TABLE_FIELD_VALUE = 'field'
    TABLE_MODEL_VALUE = 'model'

    COMMAND_IGNORE = 'IGNORE'
    COMMAND_DELETE = 'DELETE'
    COMMAND_HARDCODE = 'HC:'

    dry_run = True
    summary_only = True

    def handle(self, *args, **options):
        sub_command = options['sub-command']
        self.dry_run = options['dry_run']
        self.migration_file = options['migration_file']
        self.event_types = options['event_types']
        self.output = options['o']
        self.summary_only = options['summary']

        if sub_command not in self.SUB_COMMANDS:
            raise NameError('Command: {0} not supported'.format(sub_command))

        getattr(self, sub_command)()

    def add_arguments(self, parser):
        parser.add_argument('sub-command', type=str,
                            help='supported commands are {0}'.format(Command.SUB_COMMANDS))
        parser.add_argument('--migration-file', type=str,
                            help='input filename for migration plan')
        parser.add_argument('--event-types', nargs='+',
                            help='input list of unused eventtypes to delete')
        parser.add_argument(
            '-o', type=str, help='output filename for dumptypes')
        parser.add_argument('--summary', action='store_true',
                            help='for dumptypes, only output summary data')

        parser.add_argument('--dry-run', action='store_true',
                            help='output result only, do not save to db')

    def migrate_definition(self, event_type):
        schema_raw = event_type.schema
        schema = schema_utils.get_rendered_schema(schema_raw)[
            'properties']

    def load_standard_eventtypes(self):
        event_types = pd.read_json('./activity/fixtures/event_data_model.json')
        for index, row in event_types.iterrows():
            if row.model == 'activity.eventtype':
                fields = row.fields
                try:
                    event_type = EventType.objects.get(value=fields["value"])
                    logger.info(f"Event type {event_type} already existing")
                except Exception:
                    new_category, created = EventCategory.objects.get_or_create(
                        value=fields["category"][0])
                    event_type = EventType.objects.create(
                        id=row.pk,
                        value=fields["value"],
                        display=fields["display"],
                        ordernum=fields["ordernum"],
                        category=new_category,
                        schema=fields["schema"],
                        is_collection=fields["is_collection"])
                    logger.info(f"New event type {event_type} loadded")

    def dumptypes(self):
        # self.load_standard_eventtypes()
        if not self.output:
            raise NameError('-o output option required')

        records = self.get_all_event_type_records()

        with open(self.output, mode='w') as fh:
            fh.write(json.dumps(records, indent=4))

    CSV_HEADER = [
        'ReportCategory',
        'ReportType',
        'Model',
        'Field',
        'Value',
        'Display',
        'DisplayFR',
    ]

    def dumplocalize(self):
        """Dump records to localize
        Report Category
        Report Type Title
        Report Field Title
        Report Field Choices
        Subject Type
        Subject SubType
        """
        if not self.output:
            raise NameError('-o output option required')
        dm = self.get_all_event_type_records()
        with open(self.output, mode='w', newline='') as fh:
            csv_writer = csv.DictWriter(fh, self.CSV_HEADER, )
            csv_writer.writeheader()

            for category in EventCategory.objects.all():
                csv_writer.writerow(dict(ReportCategory=category.value,
                                         Display=category.display))

            for event_type in self.get_all_event_type_records():
                event_type_value = event_type['value']
                csv_writer.writerow(dict(ReportType=event_type_value,
                                         Display=event_type['display']))

                for field_name, field_props in event_type['rendered_schema']['schema']['properties'].items():
                    csv_writer.writerow(dict(ReportType=event_type_value,
                                             Field=field_name,
                                             Display=field_props.get('title')))
                    for value, display in field_props.get('enumNames', {}).items():
                        csv_writer.writerow(dict(ReportType=event_type_value,
                                                 Model='activity.event',
                                                 Field=field_name,
                                                 Value=value,
                                                 Display=display))

            for subject_type in SubjectType.objects.all():
                csv_writer.writerow(dict(Model='observations_subjecttype',
                                         Value=subject_type.value,
                                         Display=subject_type.display))
                for subtype in SubjectSubType.objects.all().filter(subject_type=subject_type):
                    csv_writer.writerow(dict(Model='observations_subjectsubtype',
                                             Value=subtype.value,
                                             Display=subtype.display))

    def loadlocalize(self):
        pass

    def replace_table_references_in_schema(self, schema):
        """
        take the raw schema and replace table___<ChoiceTableName>___ with
        enum___<lowercase<ChoiceTableName>>___
        :param schema:
        :return: replaced schema
        """
        table_marker = "table___"
        table_marker_len = len(table_marker)
        enum_marker = "enum___"
        end_marker = "___"

        while True:
            find_index = schema.find(table_marker)
            if len(schema) <= find_index or find_index == -1:
                break
            start = find_index + table_marker_len
            end = schema.find(end_marker, start)
            old_string = schema[start:end]
            new_string = f"{enum_marker}{old_string.lower()}{end_marker}"
            old_string = f"{table_marker}{old_string}{end_marker}"
            schema = schema.replace(old_string, new_string)

        return schema

    def get_all_event_type_records(self):
        event_types = EventType.objects.all()
        records = []
        for event_type in event_types:
            record = {'id': event_type.id,
                      'created_at': event_type.created_at,
                      'updated_at': event_type.updated_at,
                      'value': event_type.value,
                      'display': event_type.display,
                      'category_value': getattr(event_type.category, 'value', None),
                      'category_id': getattr(event_type.category, 'id', 0),
                      'ordernum': event_type.ordernum,
                      'schema': self.replace_table_references_in_schema(event_type.schema),
                      'table_schema': event_type.schema,
                      'is_collection': event_type.is_collection,
                      'count': self.get_event_type_count(event_type),
                      }

            if not self.summary_only:
                record.update(
                    {
                        'rendered_schema': self.render_schema(event_type.schema, True),
                        'fields': self.get_event_type_fields(event_type.schema),
                        'tables': self.get_event_type_lookup(event_type.schema,
                                                             'table'),
                        'queries': self.get_event_type_lookup(event_type.schema,
                                                              'query'),
                        'enums': self.get_event_type_lookup(event_type.schema,
                                                            'enum'),
                    }
                )

            records.append(record)
        return records

    @transaction.atomic
    def deleteunusedtypes(self):
        types_to_delete = self.get_unused_event_types(self.event_types)

        if not self.dry_run:
            if types_to_delete:
                logger.info('Deleting unused Event Types')
                for event_type in types_to_delete:
                    try:
                        event_type.delete()
                    except Exception as error:
                        logger.error(
                            f"Error deleting {event_type} eventtype: ", error)

    def get_unused_event_types(self, event_types=None):
        unused_event_types = []
        all_event_types = EventType.objects.all()
        if event_types:
            for event_type in self.event_types:
                try:
                    EventType.objects.get(value__iexact=event_type)
                except Exception:
                    logger.error(f"Eventtype {event_type} does not exist")
            all_event_types = EventType.objects.filter(value__in=event_types)
        for event_type in all_event_types:
            count = self.get_event_type_count(event_type)
            if not count:
                logger.info('EventType %s has 0 records associated with it',
                            event_type.value)
                unused_event_types.append(event_type)
        return unused_event_types

    @transaction.atomic
    def migratetypes(self):
        with open(self.migration_file, mode='r') as fh:
            records = json.loads(fh.read())

        self.perform_migration_on_records(records)
        choice_mapping_filename, ext = os.path.splitext(self.migration_file)
        choice_mapping_filename = f"{choice_mapping_filename}-choice_mapping.json"
        dump_choice_mapping(choice_mapping_filename)

        if self.dry_run:
            raise Exception(
                "Just-in-case exception to prevent atomic operation from completing")

    def perform_migration_on_records(self, records):
        migrated_tables = []

        for record in records:
            try:
                if 'fields' not in record:
                    continue

                self.update_event_event_type(record)
                for table in record['tables']:
                    table_name = table['table_name'].lower()
                    model, field = 'activity.event', table_name
                    if self.should_update_choice_tables(record['tables']):
                        model, field = table['model'], table['field']

                    self.migrate_choices_table(table_name, model, field)
                    migrated_tables.append(self.make_value(table_name))

            except Exception as ex:
                logger.exception(
                    "Exception while migrating types or choice table fields")
                raise

        # Need to migrate all choices tables before we muck with the stored
        # event details because of the way we look up values to convert them
        for record in records:
            try:
                if 'fields' not in record:
                    continue
                event_type = EventType.objects.get(value=record['value'])
                self.update_fields_with_event_type(
                    record, event_type, migrated_tables)
            except Exception as ex:
                logger.exception('Exception while migrating event details')
                raise

    def render_schema(self, schema, include_enums=False):
        if not schema:
            return

        if not include_enums:
            return schema_utils.render_schema_template(
                schema, schema_utils.get_empty_params(schema))
        renderer = schema_utils.get_schema_renderer_method()
        return renderer(schema)

    def get_event_type_count(self, event_type):
        for row in Event.objects.filter(event_type_id=event_type.id).values('event_type_id').annotate(ecount=Count('event_type_id')):
            return row['ecount']
        return 0

    def get_event_type_fields(self, schema):
        if not schema:
            return

        fields = list(schema_utils.get_all_fields(schema))
        return fields

    def get_event_type_lookup(self, schema, lookup):
        if not schema:
            return

        lookups = []
        for field in schema_utils.get_replacement_fields_in_schema(schema):
            if field[schema_utils.LOOKUP_ATTR] == lookup:
                if field[schema_utils.LOOKUP_ATTR] == 'table':
                    lookups.append(
                        {'table_name': field[schema_utils.FIELD_ATTR]})
                else:
                    lookups.append(field)
        return lookups

    def make_value(self, name):
        name = name.lower()
        return name.replace(' ', '_')

    def should_update_event_type(self, record):
        return self.PREVIOUS_EVENT_FIELD in record

    def should_update_choice_tables(self, tables):
        for table in tables:
            if self.TABLE_FIELD_VALUE in table and self.TABLE_MODEL_VALUE in table:
                return True
        return False

    def should_update_fields_with_event_type(self, fields):
        for field in fields:
            if self.PREVIOUS_PROPERTY_FIELD in field:
                return True
        return False

    def update_event_event_type(self, record):

        # Create all event types in the target document even if we aren't
        # migrating any actual events to the new type
        try:
            new_event_type = EventType.objects.get(value=record['value'])
            with connection.cursor() as conn:
                # ordernum can be 0, so only check for None
                if 'ordernum' in record and record['ordernum'] is not None:
                    conn.execute(
                        "UPDATE activity_eventtype SET ordernum = %s WHERE id = %s",
                        [record['ordernum'], new_event_type.id])
                if 'display' in record and record['display']:
                    conn.execute(
                        'UPDATE activity_eventtype SET display = %s WHERE id = %s',
                        [record['display'], new_event_type.id])
                if 'schema' in record and record['schema']:
                    if 'table_' in record['schema']:
                        record['schema'] = record['schema'].replace(
                            'table_', 'enum_')
                    conn.execute(
                        'UPDATE activity_eventtype SET schema = %s WHERE id = %s',
                        [record['schema'], new_event_type.id])
        except ObjectDoesNotExist:
            new_event_type = self.create_new_event_type(record)

        old_event_type_value = record.get(self.PREVIOUS_EVENT_FIELD)
        if old_event_type_value:
            old_event_type = EventType.objects.get(value=old_event_type_value)

            if old_event_type.id == new_event_type.id:
                return

            for event in Event.objects.filter(event_type_id=old_event_type.id):
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE activity_event SET event_type_id = %s WHERE id = %s', [
                                   new_event_type.id, event.id])

            with connection.cursor() as conn:
                conn.execute('DELETE FROM activity_eventtype WHERE id = %s', [
                             old_event_type.id])

    def create_new_event_type(self, event_type_data):

        category = EventCategory.objects.get(
            value=event_type_data['category_value'])

        return EventType.objects.create(id=event_type_data['id'],
                                        value=event_type_data['value'],
                                        display=event_type_data['display'],
                                        category=category,
                                        ordernum=event_type_data['ordernum'],
                                        schema=event_type_data['schema'],
                                        is_collection=event_type_data['is_collection'])

    def is_uuid(self, str):
        try:
            uuid = UUID(str)
            return True
        except ValueError:
            pass
        return False

    def should_lookup_value_for_field(self, record, previous_property_name, current_property_name, former_tables, old_data):

        # If it isn't a guid to begin with,
        if not self.is_uuid(old_data[previous_property_name]):
            return False

        # If we migrated this table, then definitely look up the value
        if self.make_value(previous_property_name) in former_tables:
            return True

        # Because some choice tables were used by multiple_schemas, see if
        # the table was migrated under a name we didn't expect
        for table in record['tables']:
            if table['field'] == current_property_name:
                return True

        return False

    def lookup_choice_value(self, table_row_id):
        # from the saved data we only have the UUID from the table and the Name
        try:
            return lookup_choice_value_by_id(table_row_id)
        except choices.Choice.DoesNotExist:
            pass

        raise ChoiceNotFoundException(
            "did not find choice by id {table_row_id}")

    def is_choice_property(self, property_id, rendered_schema):
        # simple check to see if the rendered schema has an enum for that
        # property
        properties = rendered_schema['schema']['properties']
        try:
            property_def = properties[property_id]
        except KeyError:
            logger.warning(
                f"Property {property_id} not found in event type {rendered_schema['schema']['title']}")
            return False
        if 'enum' in property_def:
            return True
        if "definition" not in rendered_schema:
            return False
        for details in rendered_schema['definition']:
            if isinstance(details, dict) and details.get('key') == property_id and 'titleMap' in details:
                return True
        return False

    def _modify_event_details(self, data, migration_plan, event_type, former_tables):
        dirty = False

        # Update choice table event_detail values
        if migration_plan['tables']:
            for property_id, details in data.items():
                if not self.is_choice_property(property_id, migration_plan['rendered_schema']):
                    continue
                if not details:
                    continue
                # seen table fields look like
                # "behavior": {"name": "Feeding", "value": "6ba1d7a5-c94a-482c-a746-25b0c4d0a877"}
                # for a multiple checkboxes "behavior":[{"name": "Feeding",
                # "value": "6ba1d7a5-c94a-482c-a746-25b0c4d0a877"}]
                if isinstance(details, str):
                    if self.is_uuid(details):
                        try:
                            data[property_id] = self.lookup_choice_value(
                                UUID(details))
                            dirty = True
                        except ChoiceNotFoundException:
                            # ignore that this might be a query lookup
                            logger.warning(
                                f'Choice not found for property {property_id} - {details}')
                else:
                    if isinstance(details, dict):
                        details = [details]
                    if not isinstance(details, list):
                        raise ChoiceException(
                            f"Unknown details type: {details}")
                    for item in details:
                        if self.is_uuid(item["value"]):
                            try:
                                item["value"] = self.lookup_choice_value(
                                    UUID(item['value']))
                                dirty = True
                            except ChoiceNotFoundException:
                                # ignore this might be a dynamic query lookup
                                logger.warning(
                                    f'Choice not found for property {property_id} - {details}')

        # Update event_detail values or names
        if self.should_update_fields_with_event_type(migration_plan['fields']):
            for field in migration_plan['fields']:
                if self.PREVIOUS_PROPERTY_FIELD in field:
                    previous_property_name = field.get(
                        self.PREVIOUS_PROPERTY_FIELD, self.COMMAND_IGNORE)
                    property_name = field.get(self.CURRENT_PROPERTY_NAME)
                    property_value = field.get(
                        self.CURRENT_PROPERTY_VALUE) \
                        or data[previous_property_name]

                    # Mapping specifies to skip this field
                    if previous_property_name == self.COMMAND_IGNORE or property_name == self.COMMAND_DELETE:
                        continue
                    try:
                        # New value is hardcoded to a specific value regardless
                        # of existing data
                        if self.COMMAND_HARDCODE in previous_property_name:
                            previous_property_name = previous_property_name.split(':')[
                                1]

                        if previous_property_name in data:
                            if self.should_lookup_value_for_field(migration_plan, previous_property_name, property_name,
                                                                  former_tables, data):
                                try:
                                    choice_object = choices.Choice.objects.get(
                                        id=data[previous_property_name])
                                    data[property_name] = str(
                                        choice_object.value)
                                except TypeError:
                                    data[property_name] = property_value
                            else:
                                data[property_name] = property_value

                            del data[previous_property_name]
                            dirty = True

                    except KeyError:
                        pass
        return data, dirty

    def update_fields_with_event_type(self, migration_plan, event_type, former_tables):
        for event in Event.objects.filter(event_type_id=event_type.id):
            for event_details_revision in event.revision.all():
                data = copy.deepcopy(event_details_revision.data)
                if not data.get("data") or not data.get("data", {}).get("event_details"):
                    continue
                details = data["data"]["event_details"]
                details, dirty = self._modify_event_details(
                    details, migration_plan, event_type, former_tables)
                if dirty:
                    data["data"]["event_details"] = details
                    with connection.cursor() as cursor:
                        cursor.execute('UPDATE activity_eventdetailsrevision SET data = %s WHERE id = %s', [
                                       json.dumps(data), event_details_revision.id])

            for event_details in event.event_details.all():
                data = copy.deepcopy(event_details.data['event_details'])
                data, dirty = self._modify_event_details(
                    data, migration_plan, event_type, former_tables)
                if dirty:
                    with connection.cursor() as cursor:
                        cursor.execute('UPDATE activity_eventdetails SET data = %s WHERE id = %s', [
                                       json.dumps({'event_details': data}), event_details.id])

    def migrate_choices_table(self, table_name, model, field):
        table_ct = ContentType.objects.get(
            app_label='choices', model=table_name)
        table = table_ct.model_class()

        for row in table.objects.all():
            # for matching pks on choices and choice tables,
            # do not create a new choice with duplicate ID
            choice_row = choices.Choice.objects.filter(id=row.id).first()

            if choice_row:

                value = self.make_value(row.name)
                if choice_row.value != value:
                    message = f'For table {table_name}, row name:{row.name}, id:{row.id}, found existing Choice row {choice_row}, Value ({value} != {choice_row.value} does not match'
                    raise ChoiceException(message)
                if choice_row.display != row.name:
                    message = f'For table {table_name}, row name:{row.name}, id:{row.id}, found existing Choice row {choice_row}, Display ({row.name} != {choice_row.display} does not match'
                    raise ChoiceException(message)

                message = f'For table {table_name}, row name:{row.name}, id:{row.id}, found existing Choice row {choice_row} but Value and Display match'
                logger.info(message)
            else:
                existing_choice = choices.Choice.objects.filter(
                    model=model, field=field, value=self.make_value(
                        row.name)).first()

                if existing_choice:
                    if existing_choice.display != row.name:
                        raise ChoiceException(f'Found matching Choice row by {model}:{field}:{self.make_value(row.name)},'
                                              f'but {existing_choice.display} != {row.name}')

                    logger.info(
                        f'Found matching Choice row by {model}:{field}:{self.make_value(row.name)}:{existing_choice.display}')

                    if existing_choice.id != row.id:
                        add_to_choice_mapping(
                            row.id, row.name, existing_choice.id)
                        logger.info(
                            f'Found matching Choice row by {model}:{field}:{self.make_value(row.name)}:{existing_choice.display}, ids are different {row.id} != {existing_choice.id}')

                else:
                    values = {
                        'id': row.id,
                        'model': model,
                        'field': field,
                        'value': self.make_value(row.name),
                        'display': row.name,
                        'ordernum': row.ordernum}

                    new_choice = choices.Choice.objects.create(**values)
                    logger.debug(
                        'New choice %s, migrated from %s table to choices',
                        new_choice.value, table_name)
