import os
import tempfile

import pytest

from django.urls import reverse

from activity.models import PRI_NONE, PRI_URGENT, SC_ACTIVE, Event, EventNote
from activity.serializers import EventNoteSerializer, EventSerializer
from revision.manager import get_object_by_id
from utils.text import humanize_field_name


@pytest.mark.django_db
class TestEventRevisionsMessage:
    def test_new_event(self, event_with_detail):
        event = event_with_detail.event

        data = EventSerializer(event).data["updates"]
        assert data[0]["message"] == "Created"

    def test_event_change_state_message(self, event_with_detail):
        event = event_with_detail.event
        event.state = SC_ACTIVE
        event.save()

        data = EventSerializer(event).data["updates"]
        assert data[0]["message"] == f"Changed State: new \u2192 {SC_ACTIVE}"

    def test_event_change_priority(self, event_with_detail):
        event = event_with_detail.event
        event.priority = PRI_URGENT
        event.save()

        data = EventSerializer(event).data["updates"]
        assert "Changed Priority: Gray \u2192 Red" in data[0]["message"]

    @pytest.mark.parametrize(
        "fields",
        [
            {"field": "title", "value": "new title"},
            {"field": "message", "value": "new description"},
        ],
    )
    def test_event_set_field_message(self, superuser_client, fields):
        payload = {
            "event_type": "acoustic_detection",
            "state": "active",
            "priority": PRI_NONE,
            "time": "2023-03-09T22:25:20.329Z",
        }

        response_create = superuser_client.post("/api/v1.0/activity/events/", payload)
        reverse("event-view", kwargs={"id": response_create.data["id"]})
        superuser_client.patch(
            reverse("event-view", kwargs={"id": response_create.data["id"]}), {fields["field"]: fields["value"]}
        )

        event = Event.objects.get(pk=response_create.data["id"])
        updates = EventSerializer(event).data["updates"]

        message = f"Added {humanize_field_name(fields['field'])}: {fields['value']}"
        result = [revision for revision in updates if message == revision["message"]]

        assert result

    @pytest.mark.parametrize(
        "fields",
        [{"field": "title", "value": "new title2"}],
    )
    def test_event_update_field_message(self, superuser_client, fields):
        payload = {
            "event_type": "acoustic_detection",
            "state": "active",
            "title": "TITLE",
            "priority": PRI_NONE,
            "time": "2023-03-09T22:25:20.329Z",
        }

        response_create = superuser_client.post(reverse("events"), payload)

        superuser_client.patch(
            reverse("event-view", kwargs={"id": response_create.data["id"]}), {fields["field"]: fields["value"]}
        )

        event = Event.objects.get(pk=response_create.data["id"])
        updates = EventSerializer(event).data["updates"]

        message = f"Changed {humanize_field_name(fields['field'])}: {payload[fields['field']]} → {fields['value']}"
        result = [revision for revision in updates if message == revision["message"]]

        assert result


@pytest.mark.django_db
class TestEventNoteRevisionsMessages:
    @pytest.mark.parametrize(
        "data",
        [
            {"text": "new note"},
            {"text": "Note 2"},
            {"text": "This a New Note"},
        ],
    )
    def test_event_add_note_message(self, superuser, five_events, data):
        data["created_by_user"] = superuser
        data["event"] = five_events[0]
        note = EventNote.objects.create(**data)

        updates = EventNoteSerializer(note).data["updates"]

        assert updates[0]["message"] == f"Note Added: {data['text']}"

    @pytest.mark.parametrize(
        "data",
        [
            {"text": "Updated note"},
            {"text": "New text"},
        ],
    )
    def test_event_update_note_message(self, superuser_client, five_event_notes, data):
        note = five_event_notes[0]
        note.text = data["text"]
        note.save()

        updates = EventNoteSerializer(note).data["updates"]

        assert updates[1]["message"] == f"Note Updated: {data['text']}"


@pytest.mark.django_db
class TestEventFileRevisionsMessages:
    @pytest.mark.parametrize(
        "payload",
        [
            {"filename": "file-text.txt", "content": " "},
            {"filename": "file-text.png", "content": "My file"},
            {"filename": "file-text.gif", "content": "The quick brown fox jumps over the lazy dog."},
        ],
    )
    def test_event_add_file_message(self, superuser_client, event_with_detail, payload):
        file_path = os.path.join(tempfile.mkdtemp(), payload["filename"])

        with open(file_path, "w") as file:
            file.write(payload["content"])

        with open(file_path, "rb") as file:
            path = reverse("event-view-files", kwargs={"id": event_with_detail.event.id})
            response = superuser_client.post(path, {"filecontent.file": file}, format="multipart")
            assert response.status_code == 201

        response = superuser_client.get(reverse("events"))
        updates = response.data["results"][0]["updates"]
        result = [revision for revision in updates if f"File Added: {payload['filename']}" in revision["message"]]

        assert result


@pytest.mark.django_db
class TestGetObjectById:
    def test_get_subject_object(self, subject):
        uuid = str(subject.id)

        obj = get_object_by_id(uuid)

        assert obj == subject

    def test_get_source_object(self, subject_source):
        source = subject_source.source
        uuid = str(source.id)

        obj = get_object_by_id(uuid)

        assert obj == source

    def test_get_community_object(self, subject_source, community):
        uuid = str(community.id)

        obj = get_object_by_id(uuid)

        assert obj == community

    def test_get_user_object(self, subject_source, community, ops_user):
        uuid = str(ops_user.id)

        obj = get_object_by_id(uuid)

        assert obj == ops_user

    def test_get_none_as_object(self, subject_source, community, ops_user):
        obj = get_object_by_id("70d7456f-32cd-47b5-83d1-a3aea03bbae0")

        assert obj is None
