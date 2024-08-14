import csv
import hashlib
import json
import logging

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from accounts.models.permissionset import PermissionSet

PERMISSION_SET_HASH_KEY = "permission_set_hash"
logger = logging.getLogger(__name__)


def get_queryset():
    return PermissionSet.objects.prefetch_related("permissions").all().order_by("das_tenant__domain", "name")


def hash_permission_set_queryset(queryset) -> str:
    queryset_list = list(
        queryset.values(
            "id",
            "name",
            "permissions__name",
            "permissions__codename",
        )
    )
    serialized_data = json.dumps(queryset_list, sort_keys=True, default=lambda x: str(x))
    hash_object = hashlib.sha256(serialized_data.encode())
    return hash_object.hexdigest()


def set_permissions_set_hash(*args, **kwargs):
    queryset = get_queryset()
    hash = hash_permission_set_queryset(queryset=queryset)
    cache.set(key=PERMISSION_SET_HASH_KEY, value=hash)


def get_permission_set_hash():
    return cache.get(key=PERMISSION_SET_HASH_KEY)


def upload_csv_file(filename):
    path = "migrations_data/csv/"

    with open(filename, "rb") as file:
        file_content = file.read()
        default_storage.save(f"{path}{filename}", ContentFile(file_content))

    logger.warning(f"File {filename} uploaded to {path}{filename}.")


def create_permissionset_csv(*args, **kwargs):
    previous_hash = get_permission_set_hash()
    current_hash = hash_permission_set_queryset(queryset=get_queryset())
    migration_filename = kwargs.get("migration_filename")

    if previous_hash != current_hash:
        file_name = f"results_{migration_filename}.csv"
        logger.warning(f"Creating CSV file: {file_name}")

        with open(file_name, "w", newline="") as csvfile:
            file = csv.writer(csvfile, delimiter=",", quotechar='"')
            for permissionset in get_queryset():
                permissions = permissionset.permissions.all().order_by("name", "codename")
                count = permissions.count()
                permissions_list = ", ".join(f"{permission.codename}" for permission in permissions)
                file.writerow([permissionset.das_tenant, permissionset.name, count, permissions_list])

        upload_csv_file(file_name)
        set_permissions_set_hash()
