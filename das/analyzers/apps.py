from django.apps import AppConfig


class AnalyzersConfig(AppConfig):
    name = 'analyzers'
    verbose_name = 'Analyzers'

    def ready(self):
        import analyzers.signals
