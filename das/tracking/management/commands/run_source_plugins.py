import logging

from django.apps import apps
from django.core.management.base import BaseCommand
from tracking.tasks import run_plugins
from tracking.models import runnable_plugins


class Command(BaseCommand):

    help = 'Run all the SourcePlugins that are ENABLED.' \
           ' For dry run use [plugin-name] [-d/--dry-run] true.' \
           'For ex: python manage.py run_source_plugins savannahplugin -d true'

    def add_arguments(self, parser):
        parser.add_argument('source_id', nargs='*', type=str)
        parser.add_argument(
            '-d', '--dry-run',
            action='store',
            dest='dry_run',
            default=False,
            help='Print latest observations than use -s=True or --show=True',
        )

    def handle(self, *args, **options):
        logger = logging.getLogger(__class__.__name__)
        dry_run = True if str(options['dry_run']).lower() == 'true' else False
        if not dry_run:
            run_plugins()
        # Assuming it will be used for one plugin at a time,
        # First plugin value will be used.
        plugin_class = None
        if options['source_id']:
            source_id = options['source_id'][0]
            source_id = [plugin for plugin in runnable_plugins
                         if plugin.__name__.lower() == source_id.lower()]
            if source_id:
                plugin_class = source_id[0]
        if plugin_class:
            for plugin in plugin_class.objects.all():
                if plugin.run_source_plugins:
                    for sp in plugin.source_plugins.filter(status='enabled'):
                        if sp.should_run():
                            if dry_run:
                                for observations in sp.plugin.fetch(
                                        sp.source, sp.cursor_data, dry_run):
                                    logger.info(observations)
