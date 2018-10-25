import logging
from datetime import datetime

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
        parser.add_argument('--unit-id',
                            help='Unit id for AwtPlugin')
        parser.add_argument('--profile', help='AwtPlugin Profile name')

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

    def plugins(self, options):
        # Filter AwtPlugin using profile option if there or fetch all AwtPlugin
        if options['profile']:
            profile_name = options['profile'].strip()
            plugins = self.plugin_class.objects.filter(name=profile_name,
                                                       status='enabled')
        else:
            plugins = self.plugin_class.objects.filter(status='enabled')
        return plugins

    def maintenance(self, options):
        for plugin in self.plugins(options):
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        run_source_plugin(sp.id)
            else:
                plugin.execute()

    def list(self, options):
        for plugin in self.plugins(options):
            awt_client = AwtClient(username=plugin.username,
                                   password=plugin.password, host=plugin.host)
            self.logger.info(awt_client.fetch_units())

    def taglist(self, options):
        for plugin in self.plugins(options):
            awt_client = AwtClient(username=plugin.username,
                                   password=plugin.password, host=plugin.host)
            self.logger.info(awt_client.fetch_tags())

    def validate_start_end_time(self, start, end=None):
        # Check Start/end should be less than now
        if start >= datetime.now():
            raise ValueError('Start time should be less than or equal to '
                             'current time')
        if end:
            if end >= datetime.now():
                raise ValueError('End time should be less than or equal to '
                                 'current time')
            if end <= start:
                raise ValueError("End time can't be less than or equal to start"
                                 " time")

    def fetch_observation(self, options):
        manufacturer_id = options['manufacturer_id']
        options['dry_run'] = "true"
        try:
            source = Source.objects.get(manufacturer_id=manufacturer_id)
        except Exception as e:
            self.logger.error('No source is linked with manufacture_id = '
                              '{0}'.format(manufacturer_id))
            raise Exception('No source is linked with manufacture_id = '
                            '{0}'.format(manufacturer_id))

        if source:
            for plugin in self.plugins(options):
                source_plugins = plugin.source_plugins.filter(
                    source=source, status='enabled')
                if source_plugins:
                    for source_plugin in source_plugins:
                        for observations in source_plugin.plugin.fetch(
                                source, source_plugin.cursor_data, options):
                            self.logger.info(observations)

    def observations(self, options):
        if not options['start_time']:
            raise ValueError('start-time is required with end-time. '
                             'Use --start-time [start-time])')
        try:
            options['start_time'] = parse(options['start_time'])
            options['end_time'] = (parse(options['end_time'])
                                   if options['end_time'] else datetime.now())
            self.validate_start_end_time(options['start_time'],
                                         options['end_time'])
        except Exception as e:
            raise e

        options['api_type'] = 'REPLAY_API'
        if options['unit_id']:
            options['unit'] = options['unit_id']
            if options['manufacturer_id']:
                self.fetch_observation(options)
            else:
                for plugin in self.plugins(options):
                    awt_client = AwtClient(username=plugin.username,
                                           password=plugin.password,
                                           host=plugin.host)
                    response = awt_client.fetch_tags()
                    if response['Result']:
                        tags = response['Tag_List']
                        for tag in tags:
                            tag_id = tag['id']
                            options['manufacturer_id'] = tag_id
                            self.fetch_observation(options)
                    else:
                        raise Exception(response)
        else:
            if options['manufacturer_id']:
                self.fetch_observation(options)
            else:
                raise ValueError('Either manufacturer-id or unit-id is required'
                                 '. Use --manufacturer-id [manufacturer-id]'
                                 ' or --unit-id [unit-id].')
