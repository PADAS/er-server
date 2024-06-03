from django.core.management.base import BaseCommand, CommandError

from core.middleware import (
    get_maintenance_message,
    is_under_maintenance,
    set_maintenance_message,
    set_maintenance_mode,
    unset_maintenance_mode,
)


class Command(BaseCommand):
    help = "Helps to enable or disable maintenance mode."

    def add_arguments(self, parser):
        parser.add_argument(
            "mode", type=str, help="Specify the mode to enable or disable maintenance mode [enable|disable|status]"
        )
        parser.add_argument("--message", type=str, help="Specify the message to show in maintenance mode (optional)")

    def handle(self, *args, **options):
        mode = options.get("mode")

        if mode == "enable":
            set_maintenance_mode()
            message = options.get("message")
            if message:
                set_maintenance_message(message)
            self.stdout.write(self.style.SUCCESS("Maintenance mode enabled"))
        elif mode == "disable":
            unset_maintenance_mode()
            self.stdout.write(self.style.SUCCESS("Maintenance mode disabled"))
        elif mode == "status":
            if is_under_maintenance():
                self.stdout.write(
                    self.style.SUCCESS("Maintenance mode is enabled: %s" % get_maintenance_message() or "No message")
                )
            else:
                self.stdout.write(self.style.SUCCESS("Maintenance mode is disabled"))
        else:
            raise CommandError("Invalid mode. Please specify 'enable' or 'disable' or 'status'")
