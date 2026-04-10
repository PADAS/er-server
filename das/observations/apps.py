from django.apps import AppConfig


class ObservationsConfig(AppConfig):
    name = "observations"
    verbose_name = "Observations"

    def ready(self):
        # Import default signals
        from . import signals  # noqa: F401

        # Segment vector tile cache invalidation: see segment_tile_cache_invalidation and
        # docs/plans/observation-segment-tile-cache-invalidation-celery.md (not loaded at startup).
        from .celery_tile_invalidation import connect_celery_tile_invalidation_cleanup

        connect_celery_tile_invalidation_cleanup()
