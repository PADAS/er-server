from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.management import BaseCommand, CommandError
from django.db import IntegrityError

from accounts.models.eula import EULA


class EulaException(Exception):
    pass


class Command(BaseCommand):
    help = 'Update EULA'

    def add_arguments(self, parser):
        parser.add_argument('--version_string', type=str,
                            help='EULA version')
        parser.add_argument('--eula', type=str,
                            help='EULA version url')

    def handle(self, *args, **options):

        version = options.get('version_string')
        url = options.get('eula')

        if version and url:
            try:
                active_eula = EULA.objects.get_active_eula()

                if active_eula.version > version:
                    raise CommandError(
                        f"new version '{version}' can not be less than or equal the active version '{active_eula.version_number}'")
            except ObjectDoesNotExist:
                pass

            try:

                eula = EULA.objects.create(version=version, eula_url=url)
                self.reset_users_eula_acceptance()
                self.stdout.write(self.style.SUCCESS(f"Successfully updated the EULA to {str(eula)}"))
            except ValidationError as ve:
                self.stderr.write(self.style.ERROR(f"Failed to create EULA {str(ve)}"))
            except IntegrityError as ie:
                self.stderr.write(self.style.ERROR(f"Failed to create EULA {str(ie)}"))

        else:
            self.stderr.write(self.style.ERROR(
                "'--url' and '--version' arguments must be provided"))

    def reset_users_eula_acceptance(self):
        User = get_user_model()
        User.objects.all().update(accepted_eula=False)

