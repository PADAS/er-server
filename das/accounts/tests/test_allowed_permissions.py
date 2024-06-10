import operator
import uuid
from functools import reduce

import pytest

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from accounts.models import PermissionSet
from accounts.utils import (
    add_tenant_to_permission_codename,
    allowed_permissions,
    filter_permissions_by_tenant,
    get_category_name_from_perm,
    method_map,
    parse_permission_codename,
)
from client_http import HTTPClient
from utils.tenant import lengthen_tenant_id, shorten_tenant_id


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAllowedPermissions:
    @pytest.mark.parametrize(
        "perms_data",
        [
            {
                "perms": [
                    "analyzer_event_read",
                    "logistics_create",
                    "view_analyzer_event_gd",
                    "add_logistics_gd",
                ],
                "deleted_category_perms": ["hello_create", "view_hello_gd"],
                "expected": ["analyzer_event", "logistics"],
                "unexpected": [
                    "analyzer_event_gd",
                    "logistics_gd",
                ],
            },
            {
                "perms": [
                    "analyzer_event_read",
                    "view_analyzer_event_gd",
                    "add_logistics_gd",
                ],
                "deleted_category_perms": ["hello_create", "view_hello_gd"],
                "expected": ["analyzer_event", "logistics_gd"],
                "unexpected": ["analyzer_event_gd"],
            },
        ],
    )
    def test_allowed_permissions(self, perms_data, basic_event_categories, tenant_settings):
        client = HTTPClient()

        perm_set = PermissionSet.objects.create(name="test_perm_set")
        q = reduce(operator.or_, (Q(codename__icontains=perm) for perm in perms_data["perms"]))
        perms = Permission.objects.filter(q)
        perm_set.permissions.add(*perms)

        content_type = ContentType.objects.get(app_label="activity", model="event")
        deleted_categories_perms = [
            Permission.objects.create(
                codename=add_tenant_to_permission_codename(tenant_settings.id, perm), content_type=content_type
            )
            for perm in perms_data["deleted_category_perms"]
        ]
        perm_set.permissions.add(*deleted_categories_perms)

        client.app_user.permission_sets.add(perm_set)
        results = allowed_permissions(client.app_user)

        for perm in perms_data["expected"]:
            assert perm in results
            for verb in results[perm]:
                assert verb not in method_map

        for perm in perms_data["unexpected"]:
            assert not [perm for result in results.keys() if perm in result]

    @pytest.mark.parametrize(
        "data",
        [
            {"perm": "test", "expected": None},
            {"perm": "+hkFNWsARFKKsTGccwgrYA:change_test_gd", "expected": "test"},
            {
                "perm": "+hkFNWsARFKKsTGccwgrYA:change_hello_category_gd",
                "expected": "hello_category",
            },
            {
                "perm": "+hkFNWsARFKKsTGccwgrYA:change_new_hello_category_gd",
                "expected": "new_hello_category",
            },
            {
                "perm": "+hkFNWsARFKKsTGccwgrYA:event_analyzer_create",
                "expected": None,
            },
            {
                "perm": "monitoring_update",
                "expected": None,
            },
            {
                "perm": "delete_logistics-test_gd",
                "expected": "logistics-test",
            },
            {
                "perm": "change_logistics test_gd",
                "expected": "logistics test",
            },
            {
                "perm": "add_logistics_0123_gd",
                "expected": "logistics_0123",
            },
            {
                "perm": "change_logistics-0123_gd",
                "expected": "logistics-0123",
            },
            {
                "perm": "view_logistics 0123_gd",
                "expected": "logistics 0123",
            },
            {
                "perm": "delete_logistics_0123_test_gd",
                "expected": "logistics_0123_test",
            },
            {
                "perm": "add_logistics-0123-test_gd",
                "expected": "logistics-0123-test",
            },
            {
                "perm": "view_logistics 0123 test_gd",
                "expected": "logistics 0123 test",
            },
            {
                "perm": "change_logistics-0123_test_gd",
                "expected": "logistics-0123_test",
            },
            {
                "perm": "delete_logistics_0123-test_gd",
                "expected": "logistics_0123-test",
            },
            {
                "perm": "view_logistics_0123-test_asd234234_234_sdf__sd_234234_gd",
                "expected": "logistics_0123-test_asd234234_234_sdf__sd_234234",
            },
            {
                "perm": "view_das-8242_gd",
                "expected": "das-8242",
            },
            {
                "perm": "view_8242-das_gd",
                "expected": "8242-das",
            },
        ],
    )
    def test_get_category_names_from_perm(self, data):
        category_name = get_category_name_from_perm(data["perm"])
        assert category_name == data["expected"]

    @pytest.mark.parametrize(
        "data",
        [
            {"perm": "test", "codename": "test", "tenant_id": None},
            {
                "perm": "+hkFNWsARFKKsTGccwgrYA:change_hello_category_gd",
                "codename": "change_hello_category_gd",
                "tenant_id": uuid.UUID("fa190535-6b00-4452-8ab1-319c73082b60"),
            },
            {
                "perm": "+hkFNWsARFKKsTGccwgrYA:Hello_category_create",
                "codename": "Hello_category_create",
                "tenant_id": uuid.UUID("fa190535-6b00-4452-8ab1-319c73082b60"),
            },
            {
                "perm": "+hkFNWsARFKKsTGccwgrYA:change_Hello_category_gd",
                "codename": "change_Hello_category_gd",
                "tenant_id": uuid.UUID("fa190535-6b00-4452-8ab1-319c73082b60"),
            },
            {
                "perm": add_tenant_to_permission_codename(
                    uuid.UUID("fa190535-6b00-4452-8ab1-319c73082b60"), "change_hello_category_gd"
                ),
                "codename": "change_hello_category_gd",
                "tenant_id": uuid.UUID("fa190535-6b00-4452-8ab1-319c73082b60"),
            },
        ],
    )
    def test_get_codename_tenant_from_perm(self, data):
        tenant_id, codename = parse_permission_codename(data["perm"])
        assert codename == data["codename"]
        assert tenant_id == data["tenant_id"]

    def test_shorten_lenthen_tenant_id(self, tenant_settings):
        short_id = shorten_tenant_id(tenant_id=tenant_settings.id)
        assert isinstance(lengthen_tenant_id(short_id), uuid.UUID)

    def test_permission_queryset_filter_by_tenant(self, tenant_settings):
        content_type = ContentType.objects.get(app_label="auth", model="permission")
        not_included = Permission.objects.create(
            name="Should not be listed",
            codename="+hkFNWsARFKKsTGccwgrYA:change_hello_category_gd",
            content_type=content_type,
        )
        included = Permission.objects.create(
            name="Should be listed",
            codename=add_tenant_to_permission_codename(
                tenant_id=tenant_settings.id, codename="change_hello_category_gd"
            ),
            content_type=content_type,
        )

        queryset = filter_permissions_by_tenant(tenant_settings=tenant_settings, queryset=Permission.objects.all())

        assert not_included not in queryset
        assert included in queryset
