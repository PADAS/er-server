from django.apps import AppConfig


class ObservationsConfig(AppConfig):
    name = "observations"
    verbose_name = "Observations"

    def ready(self):
        from . import signals  # noqa: F401
