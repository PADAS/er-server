import logging

from dateutil.parser import parse
from django.apps import apps
from django.core.management.base import BaseCommand

from observations.models import Source
from tracking.models.awt import AwtClient
from tracking.tasks import run_source_plugin


class Command(BaseCommand):
    logger = logging.getLogger(__name__)
    help = 'Run AwtPlugin maintenance.'

    SUB_COMMANDS = ('maintenance', 'observations', 'list', 'taglist')
    plugin_class = apps.get_model('tracking', 'AwtPlugin')

    def add_arguments(self, parser):
        parser.add_argument('sub-command', type=str,
                            help='supported commands are {0}'.format(
                                Command.SUB_COMMANDS))

        parser.add_argument('--start-time',
                            help='Start Date(required for getting observation')
        parser.add_argument('--end-time',
                            help='End Date(required for getting observation')

        parser.add_argument('--manufacturer-id',
                            help='Manufacture id(Tag ID), required with '
                                 '"observations" sub command')

        parser.add_argument('--dry-run',
                            help="stdout data(won't store in DB). Possible "
                                 "values [true/false]")

    def handle(self, *args, **options):
        sub_command = options['sub-command']
        if sub_command not in self.SUB_COMMANDS:
            raise NameError('Command: {0} not supported'.format(sub_command))
        if 'dry-run' in options.keys():
            if options['dry-run'].lower() not in ['true', 'false']:
                raise ValueError('Possible value for dry-run(true/false)')
        getattr(self, sub_command)(options)

    def maintenance(self, options):
        for plugin in self.plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        run_source_plugin(sp.id)
            else:
                plugin.execute()

    def list(self, options):
        for plugin in self.plugin_class.objects.filter(status='enabled'):
            awt_client = AwtClient(username=plugin.username,
                                   password=plugin.password, host=plugin.host)
            self.logger.info(awt_client.fetch_units())

    def taglist(self, options):
        for plugin in self.plugin_class.objects.filter(status='enabled'):
            awt_client = AwtClient(username=plugin.username,
                                   password=plugin.password, host=plugin.host)
            self.logger.info(awt_client.fetch_tags())

    @staticmethod
    def parse_date(input_date):
        try:
            parse(input_date)
        except Exception as e:
            raise e

    def observations(self, options):
        if 'end-time' in options.keys():
            if 'start-time' not in options.keys():
                raise ValueError('start-time is required with end-time. '
                                 'Use --start-time [start-time])')
            else:
                self.parse_date(options['start-time'])
                self.parse_date(options['end-time'])
                options['start_time'] = options['start-time']
                options['end_time'] = options['end-time']
                options.pop('start-time')
                options.pop('end-time')
        elif 'start-time' in options.keys():
            self.parse_date(options['start-time'])
            options['start_time'] = options['start-time']
            options.pop('start-time')

        if 'manufacturer-id' not in options.keys():
            raise ValueError('manufacturer-id is required. '
                             'Use --manufacturer-id [manufacturer-id]')
        else:
            manufacture_id = options['manufacturer-id']
            source = Source.objects.filter(manufacturer_id=manufacture_id)
            if source:
                options['manufacturer_id'] = manufacture_id
                options.pop('manufacturer-id')
                options['dry_run'] = "true"

                for plugin in self.plugin_class.objects.all():
                    source_plugins = plugin.source_plugins.filter(
                        source=source, status='enabled')
                    if source_plugins:
                        for source_plugin in source_plugins:
                            for observations in source_plugin.plugin.fetch(
                                    source, source_plugin.cursor_data, options):
                                self.logger.info(observations)
            else:
                raise Exception('No source is linked with manufacture_id = '
                                '{0}'.format(manufacture_id))
