import logging

from django.apps import apps
from django.core.management.base import BaseCommand

from tracking.tasks import run_source_plugin


class Command(BaseCommand):
    help = 'Run all the Vectronics SourcePlugins that are ENABLED.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-d', '--dry-run',
            action='store',
            dest='flag',
            default=False,
            help='Print latest observations than use -s=True or --show=True',
        )

    def handle(self, *args, **options):
        self.logger = logging.getLogger(__class__.__name__)
        flag = True if str(options['flag']).lower() == 'true' else False
        plugin_class = apps.get_model('tracking', 'VectronicsPlugin')

        for plugin in plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        if flag:
                            for observations in sp.plugin.fetch(
                                    sp.source, sp.cursor_data, flag):
                                self.logger.info(observations)
                        else:
                            run_source_plugin(sp.id)
            else:
                plugin.execute()
