from django.apps import AppConfig


class SchemasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "schemas"

    def ready(self):
        """Import DRF Spectacular extensions when the app is ready."""
        try:
            # Import our custom extensions to register them with DRF Spectacular
            from . import spectacular_extensions  # noqa: F401
        except ImportError:
            # Gracefully handle cases where DRF Spectacular is not available
            pass
