import operator
from functools import reduce

import pytest

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from accounts.models import PermissionSet
from accounts.utils import (allowed_permissions, get_category_name_from_perm,
                            method_map)
from client_http import HTTPClient


@pytest.mark.django_db
class TestAllowedPermissions:
    @pytest.mark.parametrize(
        "perms_data",
        [
            {
                "perms": [
                    "analyzer_event_read",
                    "logistics_create",
                    "view_analyzer_event_geographic_distance",
                    "add_logistics_geographic_distance",
                ],
                "deleted_category_perms": [
                    "hello_create, view_hello_geographic_distance"
                ],
                "expected": ["analyzer_event", "logistics"],
                "unexpected": [
                    "analyzer_event_geographic_distance",
                    "logistics_geographic_distance",
                    "hello",
                ],
            },
            {
                "perms": [
                    "analyzer_event_read",
                    "view_analyzer_event_geographic_distance",
                    "add_logistics_geographic_distance",
                ],
                "deleted_category_perms": [
                    "hello_create, view_hello_geographic_distance"
                ],
                "expected": ["analyzer_event", "logistics_geographic_distance"],
                "unexpected": ["analyzer_event_geographic_distance"],
            },
        ],
    )
    def test_allowed_permissions(self, perms_data, basic_event_categories):
        client = HTTPClient()

        perm_set = PermissionSet.objects.create(name="test_perm_set")
        q = reduce(
            operator.or_, (Q(codename__icontains=perm)
                           for perm in perms_data["perms"])
        )
        perms = Permission.objects.filter(q)
        perm_set.permissions.add(*perms)

        content_type = ContentType.objects.get(
            app_label="activity", model="event")
        deleted_categories_perms = [
            Permission.objects.create(codename=perm, content_type=content_type)
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
            assert perm not in results

    @pytest.mark.parametrize(
        "data",
        [
            {"perm": "test", "expected": None},
            {"perm": "change_test_geographic_distance", "expected": "test"},
            {
                "perm": "change_hello_category_geographic_distance",
                "expected": "hello_category",
            },
            {
                "perm": "change_new_hello_category_geographic_distance",
                "expected": "new_hello_category",
            },
            {
                "perm": "event_analyzer_create",
                "expected": None,
            },
            {
                "perm": "monitoring_update",
                "expected": None,
            },
            {
                "perm": "delete_logistics-test_geographic_distance",
                "expected": "logistics-test",
            },
            {
                "perm": "change_logistics test_geographic_distance",
                "expected": "logistics test",
            },
            {
                "perm": "add_logistics_0123_geographic_distance",
                "expected": "logistics_0123",
            },
            {
                "perm": "change_logistics-0123_geographic_distance",
                "expected": "logistics-0123",
            },
            {
                "perm": "view_logistics 0123_geographic_distance",
                "expected": "logistics 0123",
            },
            {
                "perm": "delete_logistics_0123_test_geographic_distance",
                "expected": "logistics_0123_test",
            },
            {
                "perm": "add_logistics-0123-test_geographic_distance",
                "expected": "logistics-0123-test",
            },
            {
                "perm": "view_logistics 0123 test_geographic_distance",
                "expected": "logistics 0123 test",
            },
            {
                "perm": "change_logistics-0123_test_geographic_distance",
                "expected": "logistics-0123_test",
            },
            {
                "perm": "delete_logistics_0123-test_geographic_distance",
                "expected": "logistics_0123-test",
            },
            {
                "perm": "view_logistics_0123-test_asd234234_234_sdf__sd_234234_geographic_distance",
                "expected": "logistics_0123-test_asd234234_234_sdf__sd_234234",
            },
            {
                "perm": "view_das-8242_geographic_distance",
                "expected": "das-8242",
            },
            {
                "perm": "view_8242-das_geographic_distance",
                "expected": "8242-das",
            },
        ],
    )
    def test_get_category_names_from_perm(self, data):
        category_name = get_category_name_from_perm(data["perm"])
        assert category_name == data["expected"]
