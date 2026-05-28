import os
import tempfile
from datetime import timedelta

import pytest

from django.urls import reverse
from django.utils import timezone

from activity.models import PRI_NONE, PRI_URGENT, SC_ACTIVE, Event, EventNote
from activity.serializers import EventNoteSerializer, EventSerializer
from revision.manager import (
    ACTION_DELETED,
    ACTION_RELATION_DELETED,
    get_object_by_id,
    relation_deleted,
)
from utils.text import humanize_field_name


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch", "acoustic_detection_event_type")
class TestEventRevisionsMessage:
    def test_new_event(self, event_with_detail):
        event = event_with_detail.event

        data = EventSerializer(event).data["updates"]
        assert data[0]["message"] == "Created"
        assert len(data) == 1

    def test_event_change_state_message(self, event_with_detail):
        event = event_with_detail.event
        event.state = SC_ACTIVE
        event.save()

        data = EventSerializer(event).data["updates"]
        assert data[0]["message"] == f"Changed State: new \u2192 {SC_ACTIVE}"
        assert len(data) == 2

    def test_event_change_priority(self, event_with_detail):
        event = event_with_detail.event
        event.priority = PRI_URGENT
        event.save()

        data = EventSerializer(event).data["updates"]
        assert "Changed Priority: Gray \u2192 Red" in data[0]["message"]
        assert len(data) == 2

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

    def test_event_details_patch_does_not_duplicate_state_change(self, superuser_client):
        # Reproduces the "Changed State: active → active" bogus revision row:
        # a frontend PATCH that sends both event_details and state=active on
        # an event that already has an EventDetails row triggers
        # dependent_table_updated -> Event.save (via EventDetails.save) AND a
        # second Event.save for the state field. Without refreshing
        # revision_original between the two saves, both diffs include state
        # and the updates list shows two state-change rows. The second renders
        # as "active → active" because by then state was already active in
        # the prior revision.
        create_resp = superuser_client.post(
            reverse("events"),
            {
                "event_type": "acoustic_detection",
                "state": "new",
                "priority": PRI_NONE,
                "time": "2023-03-09T22:25:20.329Z",
                "event_details": {"some_field": "initial"},
            },
            format="json",
        )
        event_id = create_resp.data["id"]

        # dependent_table_updated short-circuits within 1 second of created_at,
        # so push the event into the past to make sure the bug path runs.
        Event.objects.filter(pk=event_id).update(created_at=timezone.now() - timedelta(seconds=10))

        superuser_client.patch(
            reverse("event-view", kwargs={"id": event_id}),
            {
                "state": "active",
                "event_details": {"some_field": "updated"},
            },
            format="json",
        )

        event = Event.objects.get(pk=event_id)
        updates = EventSerializer(event).data["updates"]
        state_messages = [u["message"] for u in updates if u.get("type") == "update_event_state"]
        assert state_messages == [f"Changed State: new → {SC_ACTIVE}"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
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
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
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
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRevisionActions:
    """Cover the action branches in revision.manager.create_revision."""

    def test_delete_writes_action_deleted_revision(self, five_events):
        event = five_events[0]
        event_id = event.id
        initial_count = event.revision.count()

        event.delete()

        # Instance is unscoped after delete (pk cleared), so query via the
        # class-level descriptor with an explicit object_id filter.
        revisions = list(Event.revision.filter(object_id=event_id).order_by("sequence"))

        assert len(revisions) == initial_count + 1
        deleted = revisions[-1]
        assert deleted.action == ACTION_DELETED
        assert deleted.data == {}
        assert deleted.sequence == initial_count + 1

    def test_relation_deleted_signal_writes_revision(self, five_events):
        event, related = five_events[0], five_events[1]
        initial_count = event.revision.count()

        relation_deleted.send(
            sender=Event,
            relation=related,
            instance=event,
            related_query_name="relationship",
        )

        revisions = list(event.revision.order_by("sequence"))
        assert len(revisions) == initial_count + 1
        rel_del = revisions[-1]
        assert rel_del.action == ACTION_RELATION_DELETED
        assert rel_del.data == {
            "relation_id": str(related.id),
            "relation_model": "activity.Event",
            "related_query_name": "relationship",
        }

    def test_repeated_save_does_not_re_record_first_save_changes(self, event):
        # Two consecutive saves on the same in-memory instance must not record
        # the same field change twice. revision_original is captured in
        # post_init; without refreshing it after each save, the second save's
        # diff still compares against the pre-load snapshot and re-emits the
        # field that save #1 already persisted. This is what produced the
        # "Changed State: active → active" rows on event_details updates that
        # also dependent_table_updated → save the parent Event.
        new_priority = PRI_URGENT if event.priority != PRI_URGENT else PRI_NONE
        event.priority = new_priority
        event.save()
        event.save()

        last_two = list(event.revision.order_by("-sequence")[:2])
        second_save_revision, first_save_revision = last_two
        assert first_save_revision.data.get("priority") == new_priority
        assert "priority" not in second_save_revision.data

    def test_added_revision_stores_actual_serial_number(self, event):
        # SerialNumberModelMixin assigns a Coalesce/Subquery expression to the
        # serial_number attribute before super().save(), so the post_save
        # revision captured by RevisionMixin records the str() of the
        # expression object. After refresh_from_db reveals the real integer,
        # _sync_serial_number_into_added_revision rewrites the revision row
        # to match.
        added = event.revision.order_by("sequence").first()
        assert added.action == "added"
        assert added.data["serial_number"] == event.serial_number
        assert isinstance(added.data["serial_number"], int)

    def test_added_revision_after_recycled_object_id(self, event):
        # If an Event is deleted and a client later POSTs a new Event with
        # the same UUID (e.g. a mobile sync queue retrying an idempotent
        # upload after the row was deleted server-side), the prior
        # incarnation's revisions remain in the table as a tombstone. The
        # new ADDED revision must pick up at sequence = max + 1 — not 1 —
        # or it collides on the (das_tenant_id, object_id, sequence) unique
        # constraint and the SerialNumberModelMixin retry loop just spins
        # until it 500s.
        recycled_id = event.id
        event_type = event.event_type
        das_tenant = event.das_tenant

        event.delete()
        pre_existing = list(Event.revision.filter(object_id=recycled_id).order_by("sequence"))
        assert [r.action for r in pre_existing] == ["added", "deleted"]

        recycled = Event(
            id=recycled_id,
            event_type=event_type,
            das_tenant=das_tenant,
            title="recycled",
        )
        recycled.save()

        revisions = list(Event.revision.filter(object_id=recycled_id).order_by("sequence"))
        assert [r.action for r in revisions] == ["added", "deleted", "added"]
        new_added = revisions[-1]
        assert new_added.sequence == pre_existing[-1].sequence + 1
        # Full snapshot for ACTION_ADDED, not a partial diff against the
        # post_init snapshot.
        assert new_added.data["title"] == "recycled"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestPostInitDeferredFields:
    def test_post_init_does_not_recurse_on_deferred_field_instance(self, event, django_assert_num_queries):
        # Regression: fetching a revision-tracked model with .only() caused infinite recursion.
        # post_init → get_data_copy → serialize all fields → DeferredAttribute.__get__ →
        # refresh_from_db → from_db → post_init → ∞
        instance = Event.objects.only("id", "title").get(pk=event.pk)
        from revision.manager import Revision

        revision = Revision()
        with django_assert_num_queries(0):
            # Must complete without RecursionError and without hitting the DB.
            revision.post_init(instance)

        assert hasattr(instance, "revision_original")


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
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
