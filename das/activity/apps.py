from django.apps import AppConfig


class ActivityConfig(AppConfig):
    name = 'activity'
    verbose_name = 'Activity'

    def ready(self):
        import activity.signals
