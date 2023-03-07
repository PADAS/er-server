import pytest

from accounts.models.permissionset import PermissionSet
from activity.models import EventCategory


@pytest.mark.django_db
class TestEventCategorySignals:
    @pytest.mark.parametrize("value", ["test_1"])
    def test_create_dynamic_permissions_for_new_category(self, value):
        data = {"value": value, "display": value, "flag": "user"}
        event = EventCategory.objects.create(**data)

        permission_set = PermissionSet.objects.get(
            name=event.auto_permissionset_name)
        geo_permission_set = PermissionSet.objects.get(
            name=event.auto_geographic_permission_set_name
        )

        assert permission_set.permissions.count() == 4
        assert geo_permission_set.permissions.count() == 4

    @pytest.mark.parametrize(
        "data",
        [
            {
                "value": "das 8242",
                "display": "",
                "flag": "user",
                "expected": "das-8242",
            },
            {
                "value": "DAS 8242",
                "display": "",
                "flag": "user",
                "expected": "das-8242",
            },
            {
                "value": "new category",
                "display": "",
                "flag": "user",
                "expected": "new-category",
            },
            {
                "value": "New category",
                "display": "",
                "flag": "user",
                "expected": "new-category",
            },
            {
                "value": "my C@tegory",
                "display": "",
                "flag": "user",
                "expected": "my-ctegory",
            },
        ],
    )
    def test_slugify_event_category_value_field_for_new_categories(self, data):
        expected = data.pop("expected")
        print(f"\nExpected: {expected}")
        event = EventCategory.objects.create(**data)
        print(f"Event.value: {event.value}\n")
        assert event.value == expected

    def test_not_slugify_event_category_value_field_for_existing_categories(
            self, basic_event_categories
    ):
        for category in EventCategory.objects.all():
            pre_value = category.value
            new_display_value = f"{pre_value}_new"
            category.display = new_display_value
            category.save()

            assert pre_value == category.value
            assert new_display_value == category.display
