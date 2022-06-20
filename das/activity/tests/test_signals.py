import pytest

from activity.models import EventCategory
from accounts.models.permissionset import PermissionSet


@pytest.mark.django_db
class TestEventCategorySignals:

    @pytest.mark.parametrize("value", ['test_1'])
    def test_create_dynamic_permissions_for_new_category(self, value):
        data = {
            'value': value,
            'display': value,
            'flag': 'user'
        }
        event = EventCategory.objects.create(**data)

        permission_set = PermissionSet.objects.get(name=event.auto_permissionset_name)
        geo_permission_set = PermissionSet.objects.get(name=event.auto_geographic_permission_set_name)

        assert permission_set.permissions.count() == 4
        assert geo_permission_set.permissions.count() == 4
