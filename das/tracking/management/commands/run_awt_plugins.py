import logging
import re
from datetime import datetime, timezone
import csv
import os
import pathlib

from dateutil.parser import parse
from django.apps import apps
from django.core.management.base import BaseCommand

from observations.models import Source, SourceProvider
from tracking.models.plugin_base import SourcePlugin, DasDefaultTarget, Obs
from tracking.models.awt import AwtClient
from tracking.tasks import run_source_plugin
from tracking.pubsub_registry import notify_new_tracks


AWT_ID_CONVERSION_RE = re.compile(r'0([0-9]{7})[SKY,VTI][0-9A-Z]{4}')


def convert_skyq_tag_to_awtplugin_tag(skyq_tag_id):
    if not skyq_tag_id:
        return
    skyq_tag_id = skyq_tag_id.strip()
    matches = AWT_ID_CONVERSION_RE.match(skyq_tag_id)
    if matches:
        return matches.groups(0)[0]


class Command(BaseCommand):
    logger = logging.getLogger(__name__)
    help = 'Run AwtPlugin maintenance.'

    SUB_COMMANDS = ('maintenance', 'observations',
                    'unitlist', 'taglist', 'tagsync', 'upgrade', 'backfill')
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

        parser.add_argument('--dry-run', action='store_true',
                            help="stdout data(won't store in DB). Possible "
                                 "values [true/false]")
        parser.add_argument('--enable-replay', action='store_true',
                            help="use awt replay api as needed for 3 month backfill"
                                 "values [true/false]")
        parser.add_argument('--enable-history', action='store_true',
                            help="use awt history api as needed for historical backfill"
                                 "values [true/false]")
        parser.add_argument('--output',
                            help='Filename for csv output')
        parser.add_argument('--input',
                            help='Filename for csv input')

    def handle(self, *args, **options):
        sub_command = options['sub-command']
        if sub_command not in self.SUB_COMMANDS:
            raise NameError('Command: {0} not supported'.format(sub_command))
        getattr(self, sub_command)(options)

    def fetch_plugins(self, options):
        """Filter AwtPlugin using profile option or fetch all AwtPlugins"""
        if options['profile']:
            profile_name = options['profile'].strip()
            plugins = self.plugin_class.objects.filter(name=profile_name,
                                                       status='enabled')
        else:
            plugins = self.plugin_class.objects.filter(status='enabled')
        return plugins

    def maintenance(self, options):
        """Store latest observations in DB for sources(linked with AwtPlugin)"""
        for plugin in self.fetch_plugins(options):
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        run_source_plugin(sp.id)
            else:
                plugin.execute()

    def unitlist(self, options):
        """Stdout list of units associated with AwtClient(AwtPlugin Client)"""
        for plugin in self.fetch_plugins(options):
            awt_client = AwtClient(username=plugin.username,
                                   password=plugin.password, host=plugin.host)
            self.logger.info(f'Unit list for account {plugin.username}')
            self.logger.info(awt_client.fetch_units())

    def taglist(self, options):
        """Stdout list of tag ids associated with AwtClient(AwtPlugin Client)"""
        for plugin in self.fetch_plugins(options):
            awt_client = AwtClient(username=plugin.username,
                                   password=plugin.password, host=plugin.host)
            tags = awt_client.fetch_tags()["Tag_List"]
            self.logger.info(f'Tags for account {plugin.username}')
            self.logger.info(tags)
            fieldnames = ('id', 'type',)
            with open(options['output'], 'w', newline='') as fh:
                writer = csv.DictWriter(
                    fh, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                for tag in tags:
                    writer.writerow(tag)

    def tagsync(self, options):
        """Synchronize taglist with ER"""
        for plugin in self.fetch_plugins(options):
            plugin._maintenance()

    def validate_start_end_time(self, start, end=None):
        # Check Start/end should be less than now
        if start >= datetime.now(tz=timezone.utc):
            raise ValueError('Start time should be less than or equal to '
                             'current time')
        if end:
            if end > datetime.now(tz=timezone.utc):
                raise ValueError('End time should be less than or equal to '
                                 'current time')
            if end <= start:
                raise ValueError("End time can't be less than or equal to start"
                                 " time")

    def fetch_observations(self, options, created_callback=None):
        """get tag_id using options['manufacturer_id'] and show observations for
        same tag_id.

        Args:
            options (dict): options list

        Raises:
            Exception: specifically if the manufacturer_id is not found

        Returns:
            Obs[]: returns an array of the observations that were added
        """

        manufacturer_id = options['manufacturer_id']
        try:
            source = Source.objects.get(manufacturer_id=manufacturer_id)
        except Exception as e:
            self.logger.error('No source is linked with manufacture_id = '
                              '{0}'.format(manufacturer_id))
            raise Exception('No source is linked with manufacture_id = '
                            '{0}'.format(manufacturer_id))

        if source:
            for plugin in self.fetch_plugins(options):
                source_plugins = plugin.source_plugins.filter(
                    source=source, status='enabled')
                if source_plugins:
                    for source_plugin in source_plugins:
                        accumulator = None
                        with DasDefaultTarget() as t:
                            created_count = 0
                            for observation in source_plugin.plugin.fetch(
                                    source, source_plugin.cursor_data, options):
                                if not options['dry_run']:
                                    accumulator = t.send(observation)
                                    if accumulator['created'] > created_count:
                                        created_count += 1
                                        if created_callback:
                                            created_callback(observation)

                                self.logger.info(observation)
                        if accumulator and accumulator.get('created', 0) > 0:
                            notify_new_tracks(str(source.id))

    def set_option_times(self, options):
        if not options['start_time']:
            raise ValueError('start-time is required with end-time. '
                             'Use --start-time [start-time])')

        options['start_time'] = parse(
            options['start_time']).replace(tzinfo=timezone.utc)
        options['end_time'] = (parse(options['end_time']).replace(tzinfo=timezone.utc)
                               if options['end_time'] else datetime.now(tz=timezone.utc))
        self.validate_start_end_time(options['start_time'],
                                     options['end_time'])
        return options

    def observations(self, options):
        options = self.set_option_times(options)

        if options['manufacturer_id']:
            self.fetch_observations(options)
        elif options['unit_id']:
            options['unit'] = options['unit_id']
            for plugin in self.fetch_plugins(options):
                awt_client = AwtClient(username=plugin.username,
                                       password=plugin.password,
                                       host=plugin.host)
                response = awt_client.fetch_tags()
                if response['Result']:
                    tags = response['Tag_List']
                    for tag in tags:
                        tag_id = tag['id']
                        options['manufacturer_id'] = tag_id
                        self.fetch_observations(options)
                else:
                    raise Exception(response)
        else:
            raise ValueError('Either manufacturer-id or unit-id is required'
                             '. Use --manufacturer-id [manufacturer-id] '
                             'or --unit-id [unit-id].')

    def backfill(self, options):
        """Run a backfill operation for all tags found in the --input csv specifically the "id" column.
        If --output is specified, write out a csv with rows for any new observations found.

        Backfill per the dates specified in --start-time and --end-time

        Args:
            options ([type]): arguments passed to the command
        """
        fieldnames = ('tag_id', 'recorded_at', 'latitude',
                      'longitude', 'source_id')
        options['enable_replay'] = True
        options['enable_history'] = True
        options['use_policy_backoff_threshold'] = 10
        options = self.set_option_times(options)

        with open(options["input"], 'r') as fh:
            reader = csv.DictReader(fh)
            tagids = [tag['id'] for tag in reader]

        should_write_headers = False
        if options.get("output"):
            path = pathlib.Path(options["output"])
            should_write_headers = not path.exists
            fh = path.open('a')
        else:
            fh = open(os.devnull, "w")

        try:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            if should_write_headers:
                writer.writeheader()

            def callback_writer(tag, writer):
                def _(obs):
                    writer.writerow(dict(tag_id=tag, recorded_at=obs.recorded_at,
                                    latitude=obs.latitude, longitude=obs.longitude, source_id=obs.source.id))
                return _

            for tag in tagids:
                options['manufacturer_id'] = tag
                self.fetch_observations(options, callback_writer(tag, writer))

        finally:
            fh.close()

    def upgrade(self, options):

        # upgrade from skygistics to Awt API
        for plugin in self.fetch_plugins(options):
            awt_client = AwtClient(username=plugin.username,
                                   password=plugin.password, host=plugin.host)

            self.logger.info(
                f'Upgrading existing Skygistics sources to use plugin {plugin.name}')
            response = awt_client.fetch_tags()
            tags = response.get('Tag_List', [])
            if not tags:
                self.logger.warning(f'No tags found for plugin {plugin.name}')
                continue

            tags = [t['id'] for t in tags]

            # iterate through existing sources that match
            for source in Source.objects.filter(source_type='tracking-device'):
                mapped_manufacturer_id = convert_skyq_tag_to_awtplugin_tag(
                    source.manufacturer_id)
                if not mapped_manufacturer_id:
                    continue

                if int(mapped_manufacturer_id) not in tags:
                    continue

                provider_key = plugin.name
                source_provider, created = SourceProvider.objects.get_or_create(
                    provider_key=provider_key)

                try:
                    source_plugin = next(
                        iter(SourcePlugin.objects.filter(source=source)))
                except StopIteration:
                    continue

                self.logger.info(
                    f'Found source {source.manufacturer_id} with {source_plugin.plugin.name} upgrading to {mapped_manufacturer_id} plugin {plugin.name}')
                if options['dry_run']:
                    self.logger.info('Dry run, looking for the next one')
                    continue

                source.manufacturer_id = mapped_manufacturer_id
                source.provider = source_provider
                source.save()

                source_plugin.plugin = plugin
                source_plugin.save()
