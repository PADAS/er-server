from unittest.mock import patch

import pytest

from activity.models import Event


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
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

    def test_first_insert_reconciles_with_preexisting_rows(self, das_tenant):
        """Counter starts empty; MAX() reconciliation produces MAX+1 on first insert."""
        legacy = Event.objects.create(title="legacy-1")
        # Force a high serial_number without going through the mixin, simulating
        # rows written by bulk_create / raw SQL before the counter existed.
        Event.objects.filter(pk=legacy.pk).update(serial_number=42)
        Event.serial_number_counter_model.objects.filter(das_tenant_id=das_tenant.id).delete()

        created = Event.objects.create(title="new-after-legacy")

        assert created.serial_number == 43
        counter = Event.serial_number_counter_model.objects.get(das_tenant_id=das_tenant.id)
        assert counter.last_value == 43

    def test_drift_is_healed_on_next_call(self, das_tenant):
        """last_value below MAX(serial_number) is reconciled on the next call."""
        first = Event.objects.create(title="drift-1")
        Event.objects.filter(pk=first.pk).update(serial_number=500)
        counter = Event.serial_number_counter_model.objects.get(das_tenant_id=das_tenant.id)
        counter.last_value = 2  # simulate drift from out-of-band insert
        counter.save(update_fields=["last_value"])

        created = Event.objects.create(title="drift-2")

        assert created.serial_number == 501
        counter.refresh_from_db()
        assert counter.last_value == 501
