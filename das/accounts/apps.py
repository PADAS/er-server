from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'
    verbose_name = 'User Accounts'

    def ready(self):
        import accounts.signals