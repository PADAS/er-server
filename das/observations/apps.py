from django.apps import AppConfig


class ObservationsConfig(AppConfig):
    name = "observations"
    verbose_name = "Observations"

    def ready(self):
        # Import default signals
        from . import signals  # noqa: F401
        # Cache invalidation signals for segment tiles
        from . import signals_segments_cache  # noqa: F401
        from .celery_tile_invalidation import connect_celery_tile_invalidation_cleanup

        connect_celery_tile_invalidation_cleanup()
