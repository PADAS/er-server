import logging

from django.apps import apps
from django.core.management.base import BaseCommand

from tracking.tasks import run_source_plugin


class Command(BaseCommand):
    help = 'Run all the Savannah SourcePlugins that are ENABLED.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-d', '--dry-run',
            action='store_true',
            help='Print latest observations',
        )

    def handle(self, *args, **options):
        logger = logging.getLogger(__class__.__name__)
        dry_run = options['dry_run']

        # Get SavannahPlugin Class and fetch observations
        plugin_class = apps.get_model('tracking', 'SavannahPlugin')

        for plugin in plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        if dry_run:
                            for observations in sp.plugin.fetch(
                                    sp.source, sp.cursor_data, dry_run):
                                logger.info(observations)
                        else:
                            run_source_plugin(sp.id)
            else:
                plugin.execute()
