import operator
from functools import reduce
from typing import Iterable

import pytest

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from accounts.models import PermissionSet
from activity.models import EventCategory
from client_http import HTTPClient
from utils.categories import (
    ACTIONS,
    GEO_ACTIONS,
    EventCategoryRelatedPermissionSetActions,
    get_categories_and_geo_categories,
    make_eventcategory_permission_codename,
    make_eventcategory_permission_codename_with_tenant,
    should_apply_geographic_features,
)
from utils.tenant.thread import get_tenant_settings


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


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestEventCategoryRelatedPermissionSetActions:
    @pytest.fixture
    def event_category(self) -> EventCategory:
        event_category = EventCategory.objects.create(value="test_ec", display="test_ec")
        return event_category

    def test_is_event_category_permission_set_not_changed(self, event_category) -> None:
        related_permissions_actions = EventCategoryRelatedPermissionSetActions(event_category=event_category)

        was_changed = related_permissions_actions.is_event_category_permission_set_changed_by_user()

        assert was_changed is False

    def test_is_event_category_permission_set_changed(self, event_category) -> None:
        content_type = ContentType.objects.get(
            app_label=event_category._meta.app_label,
            model=event_category._meta.model_name,
        )
        permission_set = PermissionSet.objects.get(name=event_category.auto_permissionset_name)

        permission_set.permissions.add(
            Permission.objects.create(
                codename="_test",
                name="_test",
                content_type=content_type,
            )
        )

        related_permissions_actions = EventCategoryRelatedPermissionSetActions(event_category=event_category)

        was_changed = related_permissions_actions.is_event_category_permission_set_changed_by_user()

        assert was_changed is True

    def test_delete_permissions_sets_and_permissions_related_to_event_category(self, event_category) -> None:
        related_permissions_actions = EventCategoryRelatedPermissionSetActions(event_category=event_category)
        related_permissions_actions.delete_permissions_sets_and_permissions_related_to_event_category()

        assert not PermissionSet.objects.filter(name=event_category.auto_permissionset_name).exists()
        assert not PermissionSet.objects.filter(name=event_category.auto_geographic_permission_set_name).exists()

    @pytest.mark.parametrize("new_value", ["new_value_test", "1", "nueva_categoria", "new_cat_changed"])
    def test_update_event_category_permission_set(self, event_category, new_value) -> None:
        tenant_settings = get_tenant_settings()

        permissions_codenames = self._create_permissions_codenames(ACTIONS, new_value, tenant_settings.id)
        geo_permissions_codenames = self._create_permissions_codenames(GEO_ACTIONS, new_value, tenant_settings.id, True)

        related_permissions_actions = EventCategoryRelatedPermissionSetActions(event_category=event_category)
        related_permissions_actions.update_permission_sets_and_permissions_related(
            new_value=new_value,
            display=event_category.display,
        )

        event_category.value = new_value
        event_category.save(update_fields=["value"])

        base_qs = PermissionSet.objects.prefetch_related("permissions").all()
        permission_set = base_qs.get(name=event_category.auto_permissionset_name)
        geo_permission_set = base_qs.get(name=event_category.auto_geographic_permission_set_name)

        for codename in permissions_codenames:
            assert permission_set.permissions.filter(codename=codename).exists()

        for codename in geo_permissions_codenames:
            assert geo_permission_set.permissions.filter(codename=codename).exists()

    @pytest.mark.parametrize("new_value", ["new_value_test"])
    def test_update_event_category_permission_set_with_changed_permissions_set_and_permissions(
        self, event_category, new_value
    ):
        tenant_settings = get_tenant_settings()

        permission_set = PermissionSet.objects.get(name=event_category.auto_permissionset_name)
        permission_set.name = f"{permission_set.name}_changed"
        permission_set.save(update_fields=["name"])

        geo_permission_set = PermissionSet.objects.prefetch_related("permissions").get(
            name=event_category.auto_geographic_permission_set_name
        )
        last_permission = geo_permission_set.permissions.last()
        geo_permission_set.permissions.remove(last_permission)

        related_permissions_actions = EventCategoryRelatedPermissionSetActions(event_category=event_category)
        related_permissions_actions.update_permission_sets_and_permissions_related(
            new_value=new_value,
            display=event_category.display,
        )

        event_category.value = new_value
        event_category.save(update_fields=["value"])

        permission_set = related_permissions_actions._get_permission_set_by_name(event_category.auto_permissionset_name)

        geo_permission_set = related_permissions_actions._get_permission_set_by_name(
            event_category.auto_geographic_permission_set_name
        )

        permissions_codenames = self._create_permissions_codenames(ACTIONS, new_value, tenant_settings.id)
        geo_permissions_codenames = self._create_permissions_codenames(GEO_ACTIONS, new_value, tenant_settings.id, True)

        assert not permission_set
        assert not Permission.objects.filter(codename__in=permissions_codenames).exists()
        assert Permission.objects.filter(codename__in=geo_permissions_codenames).count() == 3

    def _create_permissions_codenames(self, actions: Iterable[str], value: str, tenant_id, is_geographic: bool = False):
        codenames = []

        for action in actions:
            codenames.append(
                make_eventcategory_permission_codename_with_tenant(
                    eventcategory_value=value,
                    action=action,
                    tenant_id=tenant_id,
                    is_geographic=is_geographic,
                )
            )
        return codenames
