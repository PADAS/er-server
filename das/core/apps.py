from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "DAS Configuration"

    def ready(self):
        import core.signals
        from utils.tenant.domains import add_new_tenant_domains_to_settings

        add_new_tenant_domains_to_settings()
