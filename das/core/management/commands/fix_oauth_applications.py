import logging

from django.core.management.base import BaseCommand

from core.models import DASApplication, DASTenant
from utils.tenant.managers import set_tenant

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create or update EFB OAuth application for all tenants"

    def handle(self, *args, **options):
        tenants = DASTenant.objects.all()
        success_count = 0
        error_count = 0

        for tenant in tenants:
            try:
                set_tenant(tenant.domain)
            except Exception as e:
                logger.error("Error setting tenant %s: %s", tenant.domain, e)
                self.stderr.write(self.style.ERROR(f"Error setting tenant {tenant.domain}: {e}"))
                error_count += 1
                continue

            efb_app, created = DASApplication.objects.get_or_create(
                client_id="EFB_APPLICATION_ID",
                defaults={
                    "client_type": "Confidential",
                    "authorization_grant_type": "password",
                    "client_secret": "",
                    "name": "Event Form Builder Das App",
                    "skip_authorization": True,
                },
            )

            action = "Created" if created else "Already exists"
            self.stdout.write(self.style.SUCCESS(f"{action}: EFB application for {tenant.domain}"))
            success_count += 1

        self.stdout.write(self.style.SUCCESS(f"\nCompleted: {success_count} tenants processed, {error_count} errors"))
