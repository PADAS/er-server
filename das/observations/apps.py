from django.apps import AppConfig


class ObservationsConfig(AppConfig):
    name = "observations"
    verbose_name = "Observations"

    def ready(self):
        # Import default signals
        # Cache invalidation signals for segment tiles
        import observations.signals_segments_cache  # noqa: F401

        from . import signals  # noqa: F401
