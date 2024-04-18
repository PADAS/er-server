"""migratewithlock.py
This file contains the custom management command to run Django migrations safely, using a lock.

see https://www.ghanei.net/django-migrations-on-kubernetes/
"""

from django.conf import settings
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connections

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
                    self.style.SUCCESS(f"Acquired migration lock with lock id {lock_id}. Proceeding with migrations.")
                )
                MigrateCommand.handle(self, *args, **options)
            finally:
                cursor.execute(f"SELECT pg_advisory_unlock({lock_id})")
