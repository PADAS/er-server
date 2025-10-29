"""migratewithlock.py
This file contains the custom management command to run Django migrations safely, using a lock.

see https://www.ghanei.net/django-migrations-on-kubernetes/
"""

from django.conf import settings
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connections

from core.middleware import maintenant_mode

DEFAULT_LOCK_ID = getattr(settings, "MIGRATE_LOCK_ID", 1000)  # just a random number


class Command(MigrateCommand):
    help = "Run Django migrations safely, using a lock"

    def add_arguments(self, parser):
        MigrateCommand.add_arguments(self, parser)
        parser.add_argument(
            "--migrate-lock-id",
            default=DEFAULT_LOCK_ID,
            type=int,
            help="The id of the advisory lock to use",
        )

    def handle(self, *args, **options):
        database = options["database"]
        if not options["skip_checks"]:
            self.check(databases=[database])

        # Get the database we're operating from
        connection = connections[database]
        # Hook for backends needing any database preparation
        connection.prepare_database()

        lock_id = options["migrate_lock_id"]
        with connection.cursor() as cursor:
            try:
                cursor.execute(f"SELECT pg_try_advisory_lock({lock_id})")
                result = cursor.fetchone()[0]
                if not result:
                    self.stdout.write(
                        self.style.WARNING(f"Another migration is already running with lock id {lock_id}.")
                    )
                    return
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Acquired migration lock with lock id {lock_id}."
                        " Proceeding with migrations for site {settings.SERVER_FQDN}."
                    )
                )
                # log_permissionsets.set_queryset_hash_to_cache()

                with maintenant_mode():
                    MigrateCommand.handle(self, *args, **options)

                # log_permissionsets.create_queryset_fixtures_if_hash_changed()

                self.stdout.write(
                    self.style.SUCCESS(f"Migration completed successfully for site {settings.SERVER_FQDN}.")
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Migration failed for site {settings.SERVER_FQDN}: {str(e)}"))
            finally:

                cursor.execute(f"SELECT pg_advisory_unlock({lock_id})")
