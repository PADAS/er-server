import io
import os

import pytest

from django.contrib.gis.geos import Point
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from activity.management.commands.restore_event import restore_event
from activity.models import Event, EventDetails
from activity.serializers import EventFileSerializer

STATIC_IMAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "mapping",
    "static",
)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRestoreEvent:
    def reduce_microseconds_precision(self, dt):
        return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)

    def fix_datetime_precision_in_event(self, values):
        for field in ["created_at", "updated_at", "sort_at", "event_time"]:
            if field in values:
                values[field] = self.reduce_microseconds_precision(values[field])
        return values

    def test_restore_single_event(self, five_events_with_details):
        first_event_details = five_events_with_details[0]
        first_event = first_event_details.event
        first_event_id = first_event.id
        first_event.location = Point(-103.313486, 20.420935)
        first_event.save()

        first_event_values = Event.objects.filter(id=first_event_id).values()[0]
        first_event.delete()

        assert not Event.objects.filter(id=first_event_id).exists()
        assert not EventDetails.objects.filter(event_id=first_event_id).exists()

        restore_event(first_event_id)

        assert Event.objects.filter(id=first_event_id).exists()
        assert EventDetails.objects.filter(event_id=first_event_id).exists()

        restored_first_event_values = Event.objects.filter(id=first_event_id).values()[0]
        restored_first_event_values.pop("serial_number")
        first_event_values.pop("serial_number")
        first_event_values = self.fix_datetime_precision_in_event(first_event_values)

        assert first_event_values == restored_first_event_values

    def test_restore_single_event_details(self, event_with_detail):
        first_event_details = event_with_detail
        first_event = first_event_details.event
        first_event_id = first_event.id

        first_event_details.data.update({"event_details": {"subjects_name": "horton", "behavior": ["standing"]}})
        first_event_details.save()

        first_event_values = Event.objects.filter(id=first_event_id).values()[0]
        first_event_details_values = EventDetails.objects.filter(id=first_event_details.id).values()[0]
        first_event.delete()

        assert not Event.objects.filter(id=first_event_id).exists()
        assert not EventDetails.objects.filter(event_id=first_event_id).exists()

        restore_event(first_event_id)

        assert Event.objects.filter(id=first_event_id).exists()
        assert EventDetails.objects.filter(event_id=first_event_id).exists()

        restored_first_event_values = Event.objects.filter(id=first_event_id).values()[0]
        restored_first_event_values.pop("serial_number")
        first_event_values.pop("serial_number")
        first_event_values = self.fix_datetime_precision_in_event(first_event_values)

        assert first_event_values == restored_first_event_values

        restored_first_event_details_values = EventDetails.objects.filter(id=first_event_details.id).values()[0]
        first_event_details_values = self.fix_datetime_precision_in_event(first_event_details_values)

        assert first_event_details_values == restored_first_event_details_values

    def test_restore_single_event_photo_and_pdf(self, five_events, user):
        first_event = five_events[0]
        first_event_id = first_event.id

        factory = APIRequestFactory()
        url = reverse("event-view-files", kwargs={"id": first_event_id})
        request = factory.get(url)
        request.user = user
        context = {"request": request}

        # Create a simple text file and add it to the event.
        file = io.StringIO()
        file.write("The quick red fox jumped over the lazy brown dog")
        file.seek(0)

        data = {
            "event": first_event_id,
            "filecontent.file": SimpleUploadedFile("file.txt", file.read().encode("utf-8"), content_type="text/plain"),
        }

        request.data = data
        serializer = EventFileSerializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        with open(os.path.join(STATIC_IMAGE_PATH, "easterisland.jpg"), "rb") as file:
            data = {
                "event": first_event_id,
                "filecontent.file": SimpleUploadedFile("easterisland.jpg", file.read(), content_type="image/jpg"),
            }
            request.data = data
            serializer = EventFileSerializer(data=data, context=context)
            serializer.is_valid(raise_exception=True)
            serializer.save()

        first_event.delete()

        assert not Event.objects.filter(id=first_event_id).exists()

        restore_event(first_event_id)

        first_event = Event.objects.get(id=first_event_id)

        restored_files = list(first_event.files.all())

        assert len(restored_files) == 2
