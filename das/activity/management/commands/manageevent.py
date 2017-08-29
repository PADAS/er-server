import logging
import copy

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.contrib.contenttypes.models import ContentType

from activity.models import EventType, Event, EventDetails
from activity import schema_utils
import choices.models as choices
from utils import json

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Event Type managment commands'
    dry_run = False

    SUB_COMMANDS = ('dumptypes', 'deleteunusedtypes', 'migratetypes')
    PREVIOUS_FIELD = 'previous_property_name'

    def handle(self, *args, **options):
        sub_command = options['sub-command']
        self.dry_run = options['dry_run']
        self.migration_file = options['migration-file']
        self.output = options['o']
        self.summary_only = options['summary']

        if sub_command not in self.SUB_COMMANDS:
            raise NameError('Command: {0} not supported'.format(sub_command))

        getattr(self, sub_command)()

    def add_arguments(self, parser):
        parser.add_argument('sub-command', type=str,
                            help='supported commands are {0}'.format(Command.SUB_COMMANDS))
        parser.add_argument('migration-file', type=str, nargs='?')
        parser.add_argument(
            '-o', type=str, help='output filename for dumptypes')
        parser.add_argument('--summary', action='store_true',
                            help='for dumptypes, only output summary data')

        parser.add_argument('--dry-run', action='store_true',
                            help='output result only, do not save to db')

    def migrate_definition(self, event_type):
        schema_raw = event_type.schema
        schema = schema_utils.get_rendered_schema(schema_raw)

    def save_event_type(self, event_type):
        logger.info('Saving EventType: %s', event_type)
        if not self.dry_run:
            event_type.save()

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
                      'category_value': event_type.category.value,
                      'category_id': event_type.category.id,
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

    def deleteunusedtypes(self):
        raise NotImplementedError("deleteunusedtypes not implemented")
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

    def migratetypes(self):
        raise NotImplementedError('migratetypes not implemented yet')

    def render_schema(self, schema):
        if not schema:
            return

        return schema_utils.render_schema_template(
            schema,
            schema_utils.get_empty_params(schema))

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
        name.replace(' ', '_')

    def should_update_fields_with_event_type(self, fields):
        for field in fields:
            if self.PREVIOUS_FIELD in field:
                return True
        return False

    def update_fields_with_event_type(self, fields, event_type):
        for event in Event.objects.filter(event_type_id=event_type.id):
            event_details = event.event_details
            if event_details:
                data = copy.copy(event_details.data)
                dirty = False
                for field in fields:
                    previous_property_name = field.get(self.PREVIOUS_FIELD)
                    property_name = field['property_name']
                    if previous_property_name:
                        try:
                            data[property_name] = data[previous_property_name]
                            del data[previous_property_name]
                            dirty = True
                        except KeyError:
                            pass

                if not self.dry_run and dirty:
                    event_details.data = data
                    event_details.save()

    def migrate_choices_table(self, table_name, model, field):
        table = ContentType.objects.get(app_label='choices', model=table_name)

        for row in table.objects.all():
            try:
                # choices tables do not support value field, blindly look
                # for matching pks
                choice_row = choices.Choice.objects.get(id=row.id)
                logger.info('For choice table %s, row name %s, found existing Choice row %s',
                            table_name, row.name, choice_row)
                continue
            except choices.Choice.DoesNotExist:
                pass

            values = {'id': row.id,
                      'model': model,
                      'field': field,
                      'value': self.make_value(row.name),
                      'display': row.name,
                      'ordernum': row.ordernum}
            if not self.dry_run:
                choice_row = choices.Choice.objects.create(**values)
