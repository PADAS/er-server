import hashlib
import json
import logging
from io import StringIO
from typing import Tuple

from django_multitenant.utils import unset_current_tenant

from django.apps import apps
from django.contrib.gis.db.models import QuerySet
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import ProgrammingError, connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Model

from core.models.core import DASTenant

MODEL_QUERYSET_HASH_KEY = "{model_name}_queryset_hash"
FILENAME_FOR_INIT_FIXTURES = "init_fixtures_{tenant_domain}_{model_name}.json"
FILENAME_FOR_RESULTS_FIXTURES = "results_fixtures_{tenant_domain}_{model_name}.json"

logger = logging.getLogger(__name__)


class LogModelIntoFixtures:
    def __init__(
        self,
        app_label: str,
        model: str,
        values_to_hash: Tuple[str],
        from_filename: str,
        relations: Tuple[str],
        odery_by: Tuple[str] = ("das_tenant", "id"),
    ) -> None:
        self.app_label = app_label
        self.model = model
        self.values_to_hash = values_to_hash
        self.from_filename = from_filename
        self.key = MODEL_QUERYSET_HASH_KEY.format(model_name=self.model)
        self.order_by = odery_by
        self.relations = relations
        self.pending_migrations = self._exists_pending_migrations()

    def create_queryset_fixtures_if_hash_changed(self) -> None:
        if self.pending_migrations:
            previous_hash = self.get_queryset_hash_from_cache()
            current_hash = self._get_queryset_hash()

            if previous_hash != current_hash:
                logger.warning(
                    f"Hash mismatch detected in '{self.app_label},{self.model}' , prev_hash={previous_hash}, current_hash={current_hash}"
                )
                self._create_fixtures_for_tenants(filename_template=FILENAME_FOR_RESULTS_FIXTURES)

    def set_queryset_hash_to_cache(self) -> None:
        if self.pending_migrations:
            logger.warning(f"Setting queryset hash to cache for model: {self.model}")
            hash = self._get_queryset_hash()
            cache.set(key=self.key, value=hash)

            self._create_fixtures_for_tenants(filename_template=FILENAME_FOR_INIT_FIXTURES)

    def get_queryset_hash_from_cache(self) -> str:
        return cache.get(key=self.key)

    def _get_model(self) -> Model:
        return apps.get_model(self.app_label, self.model)

    def _get_queryset(self) -> QuerySet:
        model = self._get_model()
        try:
            model.objects.first()
            return model.objects.values(*self.values_to_hash).all().order_by(*self.order_by)
        except ProgrammingError:
            return model.objects.none()

    def _get_queryset_hash(self) -> str:
        queryset_list = list(self._get_queryset())
        serialized_data = json.dumps(queryset_list, sort_keys=True, default=lambda x: str(x))
        hash_object = hashlib.sha256(serialized_data.encode())
        return hash_object.hexdigest()

    def _upload_file(self, filename: str):
        path = "migrations_data/json/"

        try:
            with open(filename, "rb") as file:
                file_content = file.read()
                default_storage.save(f"{path}{filename}", ContentFile(file_content))

            logger.warning(f"File {filename} uploaded to {path}{filename}.")
        except Exception:
            logger.error(f"Error when trying to upload fixture for model:{self.model} file to storage")

    def _exists_pending_migrations(self) -> bool:
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()

        return bool(executor.migration_plan(targets))

    def _create_fixtures_for_tenants(self, filename_template) -> None:
        unset_current_tenant()

        for tenant in DASTenant.objects.all():
            filename = filename_template.format(tenant_domain=tenant.domain, model_name=self.model)
            self._create_queryset_fixtures(filename=filename, tenant_domain=tenant.domain)

    def _create_queryset_fixtures(self, filename: str, tenant_domain: str) -> None:
        with open(filename, "w", newline="") as file:
            logger.warning(f"Creating fixture file: {filename} for model: {self.model}")

            output = StringIO()
            try:
                call_command(
                    "dumpdatawithtenant",
                    f"{self.app_label}.{self.model}",
                    *self.relations,
                    "--indent",
                    "4",
                    "--natural-foreign",
                    "--tenant_domain",
                    tenant_domain,
                    stdout=output,
                )
                file.write(output.getvalue())
                self._upload_file(filename=filename)
            except CommandError as error:
                logger.error(error)


values_to_hash = ("id", "name", "permissions__name", "permissions__codename")
oder_by = ("das_tenant", "id", "permissions__name", "permissions__codename")

log_permissionsets = LogModelIntoFixtures(
    app_label="accounts",
    model="PermissionSet",
    values_to_hash=values_to_hash,
    odery_by=oder_by,
    from_filename="permission_sets_after_migrations",
    relations=("auth.permission", "accounts.permissionsetpermission"),
)
