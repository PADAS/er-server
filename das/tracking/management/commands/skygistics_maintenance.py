import logging

import dateutil.parser
from django.core.management.base import BaseCommand

from tracking.models import SkygisticsSatellitePlugin


class Command(BaseCommand):
    help = 'Run skygistics plugin maintenance.'

    TEST_PLUGIN_NAME = '_test_plugin_name'
    SUB_COMMANDS = ('maintenance', 'login', 'devices', 'observations')

    def add_arguments(self, parser):
        parser.add_argument('sub-command', type=str,
                            help='supported commands are {0}'.format(
                                Command.SUB_COMMANDS))

        parser.add_argument('--profile', type=str,
                            help='plugin profile name')

        parser.add_argument('--dry-run', action='store_true',
                            help='output result only, do not save to db')

        parser.add_argument('--user', type=str, help='user login name')
        parser.add_argument('--password', type=str, help='password')
        parser.add_argument('--url', type=str, help='api url')
        parser.add_argument('--start', type=str)
        parser.add_argument('--end', type=str)
        parser.add_argument('--imei', type=str)

    def handle(self, *args, **options):
        self.logger = logging.getLogger(__class__.__name__)
        sub_command = options['sub-command']
        profile = options['profile']

        if sub_command not in self.SUB_COMMANDS:
            raise NameError('Command: {0} not supported'.format(sub_command))

        if not profile:
            sk = [SkygisticsSatellitePlugin(
                name=self.TEST_PLUGIN_NAME,
                service_username=options['user'],
                service_password=options['password'],
                service_api_url=options['url']
            ), ]
        elif profile == 'all':
            sk = SkygisticsSatellitePlugin.objects.all()
        else:
            sk = [SkygisticsSatellitePlugin.objects.get(name=profile), ]

        for ssp in sk:
            getattr(self, sub_command)(ssp, options)

    def maintenance(self, ssp, options):
        if ssp.name == self.TEST_PLUGIN_NAME:
            raise ValueError(
                'temporary test plugin not supported for maintenance')

        ssp._maintenance()
        ssp.execute()

    def login(self, ssp, options):
        ssp._login()

    def devices(self, ssp, options):
        for unit in ssp._get_unit_list():
            self.logger.info(unit)

    def observations(self, ssp, options):
        self.logger.info('fetching observations for {imei}'.format(**options))
        for observation in ssp._get_unit_observations(options['imei'],
                                                      dateutil.parser.parse(
                                                          options['start']),
                                                      dateutil.parser.parse(
                                                          options['end'])
                                                      ):
            self.logger.info(observation)
