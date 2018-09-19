from django.core.management.base import BaseCommand
from django.apps import apps
from tracking.tasks import run_source_plugin


class Command(BaseCommand):

    help = 'Run all the Vectronics SourcePlugins that are ENABLED.'

    def handle(self, *args, **options):

        plugin_class = apps.get_model('tracking', 'VectronicsPlugin')

        for plugin in plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        run_source_plugin(sp.id)
            else:
                plugin.execute()
