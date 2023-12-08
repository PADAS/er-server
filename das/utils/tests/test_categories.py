import operator
from functools import reduce

import pytest

from django.contrib.auth.models import Permission
from django.db.models import Q

from accounts.models import PermissionSet
from client_http import HTTPClient
from utils.categories import (
    get_categories_and_geo_categories,
    make_eventcategory_permission_codename,
    should_apply_geographic_features,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestCategoriesUtils:
    @pytest.mark.parametrize(
        "categories_perms",
        [
            {
                "categories": ["analyzer_event", "logistics"],
                "geo_categories": ["analyzer_event", "logistics"],
                "expected_categories": ["analyzer_event", "logistics"],
                "expected_geo_categories": [],
                "expected_categories_len": 2,
                "expected_geo_categories_len": 0,
            },
            {
                "categories": ["analyzer_event", "logistics", "security"],
                "geo_categories": ["monitoring"],
                "expected_categories": ["analyzer_event", "logistics", "security"],
                "expected_geo_categories": ["monitoring"],
                "expected_categories_len": 3,
                "expected_geo_categories_len": 1,
            },
            {
                "categories": ["analyzer_event", "logistics", "security"],
                "geo_categories": ["analyzer_event", "monitoring"],
                "expected_categories": ["analyzer_event", "logistics", "security"],
                "expected_geo_categories": ["monitoring"],
                "expected_categories_len": 3,
                "expected_geo_categories_len": 1,
            },
            {
                "categories": ["analyzer_event", "logistics", "security", "monitoring"],
                "geo_categories": [],
                "expected_categories": [
                    "analyzer_event",
                    "logistics",
                    "security",
                    "monitoring",
                ],
                "expected_geo_categories": [],
                "expected_categories_len": 4,
                "expected_geo_categories_len": 0,
            },
        ],
    )
    def test_get_categories_and_geo_categories_by_user(self, categories_perms, basic_event_categories):
        perm_set = PermissionSet.objects.create(name="test")

        perms_name = [f"{category}_read" for category in categories_perms["categories"]]
        q = reduce(operator.or_, (Q(codename__icontains=perm) for perm in perms_name))
        perms = Permission.objects.filter(q)
        perm_set.permissions.add(*perms)

        geo_perms_name = [
            f"{make_eventcategory_permission_codename(geo_category, 'view', True)}"
            for geo_category in categories_perms["geo_categories"]
        ]
        if geo_perms_name:
            q = reduce(operator.or_, (Q(codename__icontains=perm) for perm in geo_perms_name))
            perms = Permission.objects.filter(q)
            perm_set.permissions.add(*perms)

        client = HTTPClient()
        user = client.app_user
        user.permission_sets.add(perm_set)
        results = get_categories_and_geo_categories(user)

        assert len(results["categories"]) == categories_perms["expected_categories_len"]
        assert len(results["geo_categories"]) == categories_perms["expected_geo_categories_len"]

        assert results["categories"].sort() == categories_perms["expected_categories"].sort()
        assert results["geo_categories"].sort() == categories_perms["expected_geo_categories"].sort()
        assert perm_set.permissions.count() == len(categories_perms["categories"]) + len(
            categories_perms["geo_categories"]
        )

    @pytest.mark.parametrize(
        "get_geo_permission_set, expected",
        [
            (["logistics_create", "add_logistics_gd"], []),
            (["add_logistics_gd"], ["logistics"]),
            ([], []),
        ],
        indirect=["get_geo_permission_set"],
    )
    def test_should_apply_geographic_features_as_regular_user(
        self, get_geo_permission_set, expected, basic_event_categories
    ):
        client = HTTPClient()
        user = client.app_user
        user.permission_sets.add(get_geo_permission_set)
        assert should_apply_geographic_features(user) == expected

    @pytest.mark.parametrize(
        "get_geo_permission_set, expected",
        [
            (["logistics_create", "add_logistics_gd"], []),
            (["add_logistics_gd"], []),
            ([], []),
        ],
        indirect=["get_geo_permission_set"],
    )
    def test_should_apply_geographic_features_as_admin(self, get_geo_permission_set, expected, basic_event_categories):
        client = HTTPClient()
        user = client.app_user
        user.permission_sets.add(get_geo_permission_set)
        user.is_superuser = True
        user.save()
        assert should_apply_geographic_features(user) == expected
