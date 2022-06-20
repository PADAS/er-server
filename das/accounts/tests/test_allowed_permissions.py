import operator
from functools import reduce

import pytest

from django.contrib.auth.models import Permission
from django.db.models import Q

from accounts.models import PermissionSet
from accounts.utils import allowed_permissions, method_map
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
                "expected": ["analyzer_event", "logistics"],
                "unexpected": ["analyzer_event_geographic_distance", "logistics_geographic_distance"]
            },
            {
                "perms": [
                    "analyzer_event_read",
                    "view_analyzer_event_geographic_distance",
                    "add_logistics_geographic_distance",
                ],
                "expected": ["analyzer_event", "logistics_geographic_distance"],
                "unexpected": ["analyzer_event_geographic_distance"]

            },
        ],
    )
    def test_allowed_permissions(self, perms_data, basic_event_categories):
        client = HTTPClient()

        perm_set = PermissionSet.objects.create(name="test_perm_set")
        q = reduce(
            operator.or_, (Q(codename__icontains=perm) for perm in perms_data["perms"])
        )
        perms = Permission.objects.filter(q)
        perm_set.permissions.add(*perms)

        client.app_user.permission_sets.add(perm_set)
        results = allowed_permissions(client.app_user)

        for perm in perms_data["expected"]:
            assert perm in results
            for verb in results[perm]:
                assert verb not in method_map

        for perm in perms_data['unexpected']:
            assert perm not in results
