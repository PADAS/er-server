import logging
import copy

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.db.models import Count
from django.contrib.contenttypes.models import ContentType

from activity.models import EventType, Event, EventDetails, EventCategory
from activity import schema_utils
import choices.models as choices
from utils import json

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Event Type managment commands'
    dry_run = False

    SUB_COMMANDS = ('dumptypes', 'deleteunusedtypes', 'migratetypes')
    PREVIOUS_EVENT_FIELD = 'previous_value'
    PREVIOUS_PROPERTY_FIELD = 'previous_property_name'
    CURRENT_PROPERTY_NAME = 'property_name'
    TABLE_FIELD_VALUE = 'field'
    TABLE_MODEL_VALUE = 'model'

    COMMAND_IGNORE = 'IGNORE'
    COMMAND_DELETE = 'DELETE'
    COMMAND_HARDCODE = 'HC:'

    def handle(self, *args, **options):
        sub_command = options['sub-command']
        self.dry_run = options['dry_run']
        self.migration_file = options['migration_file']
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
        parser.add_argument(
            '-o', type=str, help='output filename for dumptypes')
        parser.add_argument('--summary', action='store_true',
                            help='for dumptypes, only output summary data')

        parser.add_argument('--dry-run', action='store_true',
                            help='output result only, do not save to db')

    def migrate_definition(self, event_type):
        schema_raw = event_type.schema
        schema = schema_utils.get_rendered_schema(schema_raw)['properties']

    def dumptypes(self):
        if not self.output:
            raise NameError('-o output option required')

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
                      'schema': event_type.schema,
                      'is_collection': event_type.is_collection,
                      'count': self.get_event_type_count(event_type),
                      }

            if not self.summary_only:
                record.update(
                    {
                        'rendered_schema': self.render_schema(event_type.schema),
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

        with open(self.output, mode='w') as fh:
            fh.write(json.dumps(records, indent=4))

    @transaction.atomic
    def deleteunusedtypes(self):
        types_to_delete = []
        for event_type in EventType.objects.all():
            count = self.get_event_type_count(event_type)
            if not count:
                logger.info('EventType %s has 0 records associated with it',
                            event_type.value)
                types_to_delete.append(event_type)
        if not self.dry_run:
            logger.info('Deleting unused Event Types')
            for event_type in types_to_delete:
                event_type.delete()

    @transaction.atomic
    def migratetypes(self):
        with open(self.migration_file, mode='r') as fh:
            records = json.loads(fh.read())

        migrated_tables = []

        for record in records:
            try:
                if 'fields' not in record:
                    continue

                if self.should_update_event_type(record):
                    self.update_event_event_type(record)

                if self.should_update_choice_tables(record['tables']):
                    for table in record['tables']:
                        self.migrate_choices_table(
                            table['table_name'].lower(), table['model'], table['field'])
                    migrated_tables += [self.make_value(table['table_name'])
                                        for table in record['tables']]

            except Exception as ex:
                print(ex)
                raise

        # Need to migrate all choices tables before we muck with the stored
        # event details because of the way we look up values to convert them
        for record in records:
            try:
                if 'fields' not in record:
                    continue

                if self.should_update_fields_with_event_type(record['fields']):
                    event_type = EventType.objects.get(value=record['value'])

                    self.update_fields_with_event_type(
                        record['fields'], event_type, migrated_tables)
            except Exception as ex:
                print(ex)
                raise

        if self.dry_run:
            raise Exception(
                "Just-in-case exception to prevent atomic operation from completing")

    def render_schema(self, schema):
        if not schema:
            return

        return schema_utils.render_schema_template(
            schema, schema_utils.get_empty_params(schema))

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
        old_event_type_value = record.get(self.PREVIOUS_EVENT_FIELD)
        if old_event_type_value:
            old_event_type = EventType.objects.get(value=old_event_type_value)
            new_event_type_exists = EventType.objects.filter(
                value=record['value']).count() > 0
            if not new_event_type_exists:
                self.create_new_event_type(record)
            new_event_type = EventType.objects.get(value=record.get('value'))

            if old_event_type.id == new_event_type.id:
                return

            for event in Event.objects.filter(event_type_id=old_event_type.id):
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE activity_event SET event_type_id = %s WHERE id = %s', [
                                   new_event_type.id, event.id])

    def create_new_event_type(self, event_type_data):

        category = EventCategory.objects.get(
            value=event_type_data['category_value'])

        EventType.objects.create(id=event_type_data['id'],
                                 value=event_type_data['value'],
                                 display=event_type_data['display'],
                                 category=category,
                                 ordernum=event_type_data['ordernum'],
                                 schema=event_type_data['schema'],
                                 is_collection=event_type_data['is_collection'])

    def update_fields_with_event_type(self, fields, event_type, former_tables):
        for event in Event.objects.filter(event_type_id=event_type.id):
            event_details = event.event_details.first()
            if event_details:
                new_data = {}
                old_data = copy.copy(event_details.data['event_details'])
                dirty = False
                for field in fields:
                    previous_property_name = field.get(
                        self.PREVIOUS_PROPERTY_FIELD, self.COMMAND_IGNORE)
                    property_name = field.get(self.CURRENT_PROPERTY_NAME)

                    if previous_property_name == self.COMMAND_IGNORE or property_name == self.COMMAND_DELETE:
                        continue

                    try:
                        if self.COMMAND_HARDCODE in previous_property_name:
                            new_data[property_name] = previous_property_name.split(':')[
                                1]
                        elif previous_property_name in old_data:
                            if previous_property_name in former_tables and isinstance(old_data[previous_property_name], dict):
                                try:
                                    choice_object = choices.Choice.objects.get(
                                        id=old_data[previous_property_name])
                                    new_data[property_name] = str(
                                        choice_object.id)
                                except TypeError:
                                    new_data[property_name] = old_data[
                                        previous_property_name]
                            else:
                                new_data[property_name] = old_data[previous_property_name]
                        dirty = True
                    except KeyError:
                        pass

                if dirty:
                    with connection.cursor() as cursor:
                        cursor.execute('UPDATE activity_eventdetails SET data = %s WHERE id = %s', [
                                       json.dumps({'event_details': new_data}), event_details.id])

    def migrate_choices_table(self, table_name, model, field):
        table_ct = ContentType.objects.get(
            app_label='choices', model=table_name)
        table = table_ct.model_class()

        for row in table.objects.all():
            try:
                # choices tables do not support value field, blindly look
                # for matching pks
                choice_row = choices.Choice.objects.get(id=row.id)
                logger.info('For choice table %s, row name %s, found existing Choice row %s',
                            table_name, row.name, choice_row)
                if choice_row.display == row.name and choice_row.id == row.id:
                    logger.info(
                        "And it already has all the correct values, so it's okay to leave it")
                    continue
                else:
                    raise Exception
            except choices.Choice.DoesNotExist:
                pass

            values = {'id': row.id,
                      'model': model,
                      'field': field,
                      'value': self.make_value(row.name),
                      'display': row.name,
                      'ordernum': row.ordernum}

            choices.Choice.objects.create(**values)
