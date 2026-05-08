from unittest.mock import patch

import pytest

from activity.models import Event


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestEvent:
    def test_delete_geometries_updates_event(self, event_geometry_with_polygon):
        with patch.object(Event, "dependent_table_updated") as event_updated_mock:
            event = event_geometry_with_polygon.event
            event.geometries.all().delete()

            event_updated_mock.assert_called_once()


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestSerialNumberOnEventModel:
    def test_serial_number_added_on_save(self):
        event_1 = Event(title="Test Event 1")
        event_1.save()
        event_2 = Event(title="Test Event 2")
        event_2.save()
        event_3 = Event(title="Test Event 3")
        event_3.save()

        assert event_1.serial_number == 1
        assert event_2.serial_number == 2
        assert event_3.serial_number == 3

    def test_serial_number_added_on_create(self):
        event_1 = Event.objects.create(title="Test Event 1")
        event_2 = Event.objects.create(title="Test Event 2")
        event_3 = Event.objects.create(title="Test Event 3")

        assert event_1.serial_number == 1
        assert event_2.serial_number == 2
        assert event_3.serial_number == 3
