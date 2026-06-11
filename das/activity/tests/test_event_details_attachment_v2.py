"""Tests for V2 event-type attachment field handling in EventDetailsSerializer (ERA-13273).

Write path: any well-formed UUID passes.  Validation is format-only — it does not
check ownership, existence, or file type.  Real access control comes from UUID
unguessability, not from write-time checks.

Metadata sidecar: EventDetails.data["metadata"]["attachments"] stores a ``{}``
placeholder for each UUID present in an attachment slot at write time.  The
top-level ``metadata`` key is hydrated at read time via ``get_attachment_info``
into ``{status, file_type, files}`` entries.

Read path: event_details returns the raw stored UUID, not a proxy URL.
Proxy URLs appear only in ``metadata.attachments.<uuid>.files`` for
``status="complete"`` attachments.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

import utils.tenant.thread as _thread_mod
from activity.filters import EventPermissionsFilter
from activity.models import Event, EventDetails, EventType
from activity.schemas.eventtype_service import (
    AttachmentField,
    AttachmentSlot,
    EventTypeSchemaService,
    SchemaResult,
    Slot,
)
from activity.serializers import EventSerializer
from activity.serializers.event_details import (
    EventDetailsSerializer,
    _collect_attachment_uuids,
)
from core.models import DASTenant
from factories import EventCategoryFactory, EventTypeFactory
from usercontent import upload_sessions
from usercontent.models import FileContent, ImageFileContent
from utils.tenant.thread import get_tenant_settings

User = get_user_model()


# ---------------------------------------------------------------------------
# Schema builders for attachment fields
# ---------------------------------------------------------------------------

_V2_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _attachment_event_type_schema(
    field_name: str = "photo",
    allowable_file_types: list[str] | None = None,
) -> dict[str, Any]:
    """Build a minimal V2 schema with a single top-level ATTACHMENT field."""
    if allowable_file_types is None:
        allowable_file_types = []
    return {
        "json": {
            "$schema": _V2_DRAFT,
            "type": "object",
            "properties": {
                field_name: {
                    "deprecated": False,
                    "title": field_name.replace("_", " ").title(),
                    "type": "string",
                }
            },
            "required": [],
            "unevaluatedProperties": False,
        },
        "ui": {
            "fields": {
                field_name: {
                    "allowableFileTypes": allowable_file_types,
                    "type": "ATTACHMENT",
                    "parent": "section-1",
                }
            },
            "headers": {},
            "order": ["section-1"],
            "sections": {
                "section-1": {
                    "columns": 1,
                    "isActive": True,
                    "label": "",
                    "leftColumn": [{"name": field_name, "type": "field"}],
                    "rightColumn": [],
                }
            },
        },
    }


def _collection_attachment_schema(
    collection_name: str = "items",
    attachment_field: str = "photo",
    allowable_file_types: list[str] | None = None,
) -> dict[str, Any]:
    """Build a V2 schema with an ATTACHMENT inside a COLLECTION."""
    if allowable_file_types is None:
        allowable_file_types = []
    return {
        "json": {
            "$schema": _V2_DRAFT,
            "type": "object",
            "properties": {
                collection_name: {
                    "deprecated": False,
                    "items": {
                        "type": "object",
                        "properties": {
                            attachment_field: {
                                "deprecated": False,
                                "title": attachment_field.replace("_", " ").title(),
                                "type": "string",
                            }
                        },
                        "required": [],
                        "type": "object",
                        "unevaluatedProperties": False,
                    },
                    "title": collection_name.replace("_", " ").title(),
                    "type": "array",
                    "unevaluatedItems": False,
                }
            },
            "required": [],
            "unevaluatedProperties": False,
        },
        "ui": {
            "fields": {
                collection_name: {
                    "buttonText": "Add",
                    "columns": 1,
                    "itemIdentifier": "",
                    "itemName": "Item",
                    "leftColumn": [attachment_field],
                    "rightColumn": [],
                    "type": "COLLECTION",
                    "parent": "section-1",
                },
                attachment_field: {
                    "allowableFileTypes": allowable_file_types,
                    "type": "ATTACHMENT",
                    "parent": collection_name,
                },
            },
            "headers": {},
            "order": ["section-1"],
            "sections": {
                "section-1": {
                    "columns": 1,
                    "isActive": True,
                    "label": "",
                    "leftColumn": [{"name": collection_name, "type": "field"}],
                    "rightColumn": [],
                }
            },
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_category():
    return EventCategoryFactory.create(value="attachment_test_cat")


@pytest.fixture
def v2_attachment_event_type(event_category):
    return EventTypeFactory.create(
        category=event_category,
        value="v2_attachment_test",
        schema=json.dumps(_attachment_event_type_schema("photo", ["image"])),
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_no_filter_attachment_event_type(event_category):
    return EventTypeFactory.create(
        category=event_category,
        value="v2_no_filter_attachment",
        schema=json.dumps(_attachment_event_type_schema("doc", [])),
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_collection_attachment_event_type(event_category):
    return EventTypeFactory.create(
        category=event_category,
        value="v2_collection_attachment",
        schema=json.dumps(_collection_attachment_schema("arrests", "arrestee_photo", ["image"])),
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v1_event_type(event_category):
    v1_schema = json.dumps(
        {
            "schema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {"photo": {"type": "string", "title": "Photo"}},
            },
            "definition": [{"key": "photo"}],
        }
    )
    return EventTypeFactory.create(
        category=event_category,
        value="v1_with_photo_field",
        schema=v1_schema,
        version=EventType.VersionChoices.VERSION_1,
    )


@pytest.fixture
def v2_empty_schema_event_type(event_category):
    """V2 event type with an empty dict as raw schema — unrenderable."""
    return EventTypeFactory.create(
        category=event_category,
        value="v2_empty_schema_test",
        schema="{}",
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_invalid_json_schema_event_type(event_category):
    """V2 event type with invalid JSON as raw schema — unrenderable."""
    return EventTypeFactory.create(
        category=event_category,
        value="v2_invalid_json_schema_test",
        schema="not valid json {{",
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_no_attachment_event_type(event_category):
    """V2 event type with a valid schema that has no attachment fields."""
    schema = {
        "json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "notes": {"type": "string", "title": "Notes"},
            },
            "required": [],
        },
        "ui": {
            "fields": {
                "notes": {"type": "TEXT", "parent": "section-1"},
            },
            "headers": {},
            "order": ["section-1"],
            "sections": {
                "section-1": {
                    "columns": 1,
                    "isActive": True,
                    "label": "",
                    "leftColumn": [{"name": "notes", "type": "field"}],
                    "rightColumn": [],
                }
            },
        },
    }
    return EventTypeFactory.create(
        category=event_category,
        value="v2_no_attachment_test",
        schema=json.dumps(schema),
        version=EventType.VersionChoices.VERSION_2,
    )


def _make_event(event_type, user):
    return Event.objects.create(
        title="Test event",
        event_type=event_type,
        created_by_user=user,
        state="new",
    )


def _make_request(user):
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = user
    return request


def _insert_filecontent(*, user, filename: str = "photo.jpg") -> FileContent:
    uid = uuid.uuid4()
    fc = FileContent(id=uid, filename=filename, created_by=user)
    fc.file.name = f"tenant/file_uploads/2024/1/1/{uid}/{filename}"
    FileContent.objects.bulk_create([fc])
    return FileContent.objects.get(id=uid)


def _insert_imagefilecontent(*, user, filename: str = "photo.jpg") -> ImageFileContent:
    uid = uuid.uuid4()
    ifc = ImageFileContent(id=uid, filename=filename, created_by=user)
    ifc.file.name = f"tenant/image_fileuploads/2024/1/1/{uid}/{filename}"
    ImageFileContent.objects.bulk_create([ifc])
    return ImageFileContent.objects.get(id=uid)


# ---------------------------------------------------------------------------
# Unit tests for SchemaResult.extract_attachment_slots
# ---------------------------------------------------------------------------


class TestExtractAttachmentSlots:
    """Pure-unit tests for SchemaResult.extract_attachment_slots."""

    def _result(self, schema: dict[str, Any]) -> SchemaResult:
        return SchemaResult(event_type_value="test", schema=schema)

    def test_flat_attachment_field(self) -> None:
        rendered = _attachment_event_type_schema("photo", ["image"])
        slots = self._result(rendered).extract_attachment_slots()
        assert "photo" in slots
        assert slots["photo"].collection_parent is None
        assert slots["photo"].field.type == "ATTACHMENT"
        assert slots["photo"].field.allowable_file_types == ["image"]

    def test_collection_nested_attachment(self) -> None:
        rendered = _collection_attachment_schema("arrests", "arrestee_photo", ["image"])
        slots = self._result(rendered).extract_attachment_slots()
        assert "arrestee_photo" in slots
        assert slots["arrestee_photo"].collection_parent == "arrests"

    def test_no_attachment_fields_returns_empty(self) -> None:
        rendered = {
            "ui": {
                "fields": {
                    "name": {"type": "TEXT", "parent": "section-1"},
                }
            }
        }
        slots = self._result(rendered).extract_attachment_slots()
        assert slots == {}

    def test_missing_ui_returns_empty(self) -> None:
        slots = self._result({}).extract_attachment_slots()
        assert slots == {}

    def test_schema_none_raises_value_error(self) -> None:
        """extract_attachment_slots must raise ValueError when schema is None."""
        result = SchemaResult(event_type_value="test", schema=None)
        with pytest.raises(ValueError, match="extract_attachment_slots requires a parsed schema"):
            result.extract_attachment_slots()

    def test_malformed_ui_field_raises(self) -> None:
        """A non-dict value in ui.fields raises ValueError naming the offending field."""
        schema = {"ui": {"fields": {"weird": "not-a-dict"}}}
        with pytest.raises(ValueError, match="weird"):
            self._result(schema).extract_attachment_slots()


# ---------------------------------------------------------------------------
# Unit tests for Slot.value_containers
# ---------------------------------------------------------------------------


class TestSlotValueContainers:
    """Pure-unit tests for Slot.value_containers."""

    def _flat_slot(self, field_name: str = "photo") -> AttachmentSlot:
        return Slot(
            field=AttachmentField(parent="section-1", allowable_file_types=[]),
            parent_is_collection=False,
        )

    def _collection_slot(self, collection_name: str = "items") -> AttachmentSlot:
        return Slot(
            field=AttachmentField(parent=collection_name, allowable_file_types=[]),
            parent_is_collection=True,
        )

    def test_flat_slot_yields_data_itself(self) -> None:
        """A flat slot yields data with the same object identity so mutations propagate."""
        slot = self._flat_slot()
        data: dict[str, Any] = {"photo": "abc"}
        result = list(slot.value_containers(data))
        assert result == [data]
        assert result[0] is data

    def test_collection_slot_yields_each_dict_item(self) -> None:
        """A collection-nested slot yields each dict in the enclosing list."""
        slot = self._collection_slot("items")
        item1: dict[str, Any] = {"photo": "uuid-1"}
        item2: dict[str, Any] = {"photo": "uuid-2"}
        data: dict[str, Any] = {"items": [item1, item2]}
        result = list(slot.value_containers(data))
        assert result == [item1, item2]
        assert result[0] is item1
        assert result[1] is item2

    @pytest.mark.parametrize(
        "data",
        [
            {},
            {"items": "not-a-list"},
        ],
        ids=["key_missing", "key_holds_non_list"],
    )
    def test_collection_parent_absent_or_non_list_yields_nothing(self, data: dict[str, Any]) -> None:
        """When the collection parent key is absent or not a list, no containers are yielded."""
        slot = self._collection_slot("items")
        result = list(slot.value_containers(data))
        assert result == []

    def test_non_dict_items_in_collection_are_skipped(self) -> None:
        """Non-dict entries in the collection list are skipped; only dicts are yielded."""
        slot = self._collection_slot("items")
        valid_item: dict[str, Any] = {"photo": "uuid-1"}
        data: dict[str, Any] = {"items": [valid_item, "not-a-dict", 42, None]}
        result = list(slot.value_containers(data))
        assert result == [valid_item]
        assert result[0] is valid_item


# ---------------------------------------------------------------------------
# Write-path validation tests (UUID format only)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestV2AttachmentWriteValidation:
    """Validate attachment field values on EventDetailsSerializer.to_internal_value.

    Validation is FORMAT-ONLY: any well-formed UUID passes.  Ownership, existence,
    and file-type are not checked at write time — only non-string values and
    malformed UUID strings are rejected.  Real access control comes from UUID
    unguessability.
    """

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _serializer(self, event_type, user=None):
        if user is None:
            user = self.user
        request = _make_request(user)
        event = _make_event(event_type, user)
        return EventDetailsSerializer(instance=event, context={"request": request})

    def test_null_value_passes(self, v2_attachment_event_type) -> None:
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": None})
        assert result["photo"] is None

    def test_empty_string_passes(self, v2_attachment_event_type) -> None:
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": ""})
        assert result["photo"] == ""

    def test_omitted_field_passes(self, v2_attachment_event_type) -> None:
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {})
        assert "photo" not in result

    def test_non_uuid_string_rejected(self, v2_attachment_event_type) -> None:
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": "not-a-uuid"})
        assert "photo" in exc_info.value.detail

    def test_non_string_value_rejected(self, v2_attachment_event_type) -> None:
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": 12345})
        assert "photo" in exc_info.value.detail

    def test_attachment_field_accepts_unknown_uuid(self, v2_attachment_event_type) -> None:
        """A well-formed UUID with no matching session or DB row passes (validation is format-only)."""
        random_uuid = str(uuid.uuid4())
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": random_uuid})
        assert result["photo"] == random_uuid

    def test_attachment_field_accepts_uuid_without_ownership_check(self, v2_attachment_event_type) -> None:
        """A UUID for an existing file passes; write validation does not verify ownership.

        Real protection comes from UUID unguessability, not from a write-time owner check.
        """
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": str(ifc.id)})
        assert result["photo"] == str(ifc.id)

    def test_attachment_field_does_not_enforce_allowable_file_types(self, v2_attachment_event_type) -> None:
        """A UUID whose file type differs from allowableFileTypes passes (validation is format-only)."""
        fc = _insert_filecontent(user=self.user, filename="notes.pdf")
        ser = self._serializer(v2_attachment_event_type)
        # v2_attachment_event_type only allows "image"; a PDF passes
        result = ser._to_internal_value_inner(ser.instance, {"photo": str(fc.id)})
        assert result["photo"] == str(fc.id)

    def test_no_allowable_file_types_accepts_any_type(self, v2_no_filter_attachment_event_type) -> None:
        fc = _insert_filecontent(user=self.user, filename="notes.pdf")
        ser = self._serializer(v2_no_filter_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"doc": str(fc.id)})
        assert result["doc"] == str(fc.id)

    def test_v1_event_type_unaffected(self, v1_event_type) -> None:
        """V1 event types must not go through attachment validation."""
        ser = self._serializer(v1_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": "not-a-uuid"})
        # V1 path: no exception, value returned as-is
        assert result["photo"] == "not-a-uuid"

    def test_no_request_context_does_not_raise_when_attachment_slots_present(self, v2_attachment_event_type) -> None:
        """With no request in context, validation still runs (format-only) without RuntimeError."""
        event = _make_event(v2_attachment_event_type, self.user)
        ser = EventDetailsSerializer(instance=event, context={})
        random_uuid = str(uuid.uuid4())
        # Format-only validation; a well-formed UUID passes even without request
        result = ser._to_internal_value_inner(event, {"photo": random_uuid})
        assert result["photo"] == random_uuid

    def test_collection_nested_attachment_valid(self, v2_collection_attachment_event_type) -> None:
        ifc = _insert_imagefilecontent(user=self.user, filename="arrestee.jpg")
        ser = self._serializer(v2_collection_attachment_event_type)
        data = {"arrests": [{"arrestee_photo": str(ifc.id)}]}
        result = ser._to_internal_value_inner(ser.instance, data)
        assert result["arrests"][0]["arrestee_photo"] == str(ifc.id)

    def test_collection_nested_invalid_uuid_rejected(self, v2_collection_attachment_event_type) -> None:
        ser = self._serializer(v2_collection_attachment_event_type)
        data = {"arrests": [{"arrestee_photo": "not-a-uuid"}]}
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, data)
        assert "arrestee_photo" in exc_info.value.detail

    # ------------------------------------------------------------------
    # Upload-session (initiated/in-progress) tests
    # ------------------------------------------------------------------

    def _seed_upload_session(
        self,
        *,
        upload_id: str | None = None,
        filename: str = "upload.jpg",
        user_id: str | None = None,
    ) -> str:
        uid = upload_id or str(uuid.uuid4())
        tenant_id = str(get_tenant_settings().id)
        upload_sessions.create(
            tenant_id,
            uid,
            storage_path=f"tenant/image_fileuploads/2024/1/1/{uid}/{filename}",
            filename=filename,
            size=1024,
            chunk_size=512,
            user_id=user_id or str(self.user.pk),
            is_image=True,
            file_content_id=uid,
        )
        return uid

    def test_initiated_upload_session_passes_validation(self, v2_attachment_event_type) -> None:
        """A live Redis upload session UUID (no DB row yet) passes format validation."""
        uid = self._seed_upload_session(filename="photo.jpg")
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": uid})
        assert result["photo"] == uid

    def test_attachment_field_accepts_in_progress_session_uuid(self, v2_attachment_event_type) -> None:
        """An in-progress upload-session UUID passes format validation (no ownership check)."""
        other = User.objects.create_user(
            "att-session-other",
            "att-session-other@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )
        uid = self._seed_upload_session(user_id=str(other.pk), filename="photo.jpg")
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": uid})
        assert result["photo"] == uid

    def test_session_from_different_tenant_uuid_still_valid_format(
        self,
        v2_attachment_event_type,
    ) -> None:
        """A UUID seeded under another tenant still has valid format and passes write validation."""
        other_tenant_id = uuid.uuid4()
        uid = str(uuid.uuid4())

        current = _thread_mod.get_tenant_settings()
        other_tenant = dataclasses.replace(current, id=other_tenant_id)

        local_thread = _thread_mod._get_local_thread()
        setattr(local_thread, _thread_mod.TENANT_DEFAULT_KEY, other_tenant)
        try:
            upload_sessions.create(
                str(other_tenant_id),
                uid,
                storage_path=f"other/path/{uid}/photo.jpg",
                filename="photo.jpg",
                size=512,
                chunk_size=256,
                user_id=str(self.user.pk),
                is_image=True,
                file_content_id=uid,
            )
        finally:
            setattr(local_thread, _thread_mod.TENANT_DEFAULT_KEY, current)

        # With the original tenant restored, the UUID still has valid format → passes
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": uid})
        assert result["photo"] == uid

    def test_other_tenant_filecontent_uuid_passes_write_validation(
        self,
        v2_attachment_event_type,
    ) -> None:
        """A finalized ImageFileContent row from another tenant passes write validation (format-only)."""
        other_tenant_id = uuid.uuid4()
        other_das_tenant = DASTenant.objects.create(
            id=other_tenant_id,
            domain=f"other-att-{other_tenant_id.hex[:12]}.example.com",
        )

        other_ifc_id = uuid.uuid4()
        other_ifc = ImageFileContent(
            id=other_ifc_id,
            filename="other_tenant.jpg",
            created_by=self.user,
            das_tenant=other_das_tenant,
        )
        other_ifc.file.name = f"other/image_fileuploads/2024/1/1/{other_ifc_id}/other_tenant.jpg"
        ImageFileContent.objects.bulk_create([other_ifc])

        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": str(other_ifc_id)})
        assert result["photo"] == str(other_ifc_id)

    # ------------------------------------------------------------------
    # Unrenderable V2 schema → 400 tests
    # ------------------------------------------------------------------

    def test_empty_raw_schema_raises_400(self, v2_empty_schema_event_type) -> None:
        """V2 event type with an empty dict as raw schema raises ValidationError (400)."""
        ser = self._serializer(v2_empty_schema_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"some_field": "value"})
        assert "unparseable V2 schema" in str(exc_info.value.detail)

    def test_invalid_json_schema_raises_400(self, v2_invalid_json_schema_event_type) -> None:
        """V2 event type with invalid JSON schema raises ValidationError (400)."""
        ser = self._serializer(v2_invalid_json_schema_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"some_field": "value"})
        assert "unparseable V2 schema" in str(exc_info.value.detail)

    def test_valid_schema_no_attachment_slots_passes(self, v2_no_attachment_event_type) -> None:
        """V2 event type with valid schema and no attachment slots accepts any data."""
        ser = self._serializer(v2_no_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"notes": "hello"})
        assert result["notes"] == "hello"

    def test_valid_schema_with_attachment_slot_and_valid_uuid_passes(self, v2_attachment_event_type) -> None:
        """V2 event type with attachment slot + valid UUID accepts the data."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": str(ifc.id)})
        assert result["photo"] == str(ifc.id)


# ---------------------------------------------------------------------------
# End-to-end integration tests through EventSerializer (create + update paths)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestV2AttachmentEndToEndValidation:
    """Integration tests for format-only attachment validation on the full EventSerializer path.

    Unknown UUIDs and file-type mismatches succeed on create and update.  The read path
    returns the raw stored UUID in event_details and surfaces status in metadata.attachments.
    """

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _context(self, user=None) -> dict[str, Any]:
        if user is None:
            user = self.user
        request = _make_request(user)
        request.build_absolute_uri = lambda path: f"http://testserver{path}"
        return {"request": request}

    def _create_serializer(self, event_type_value: str, event_details: dict[str, Any]) -> Any:
        data = {
            "event_type": event_type_value,
            "title": "Test Event",
            "event_details": event_details,
        }
        return EventSerializer(data=data, context=self._context())

    def _update_serializer(self, event, event_details: dict[str, Any]) -> Any:
        return EventSerializer(instance=event, data={"event_details": event_details}, context=self._context())

    # -- CREATE path --

    def test_create_unknown_uuid_succeeds(self, v2_attachment_event_type) -> None:
        """An unknown UUID on CREATE succeeds (validation is format-only)."""
        unknown_uuid = str(uuid.uuid4())
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": unknown_uuid})
        assert ser.is_valid(), ser.errors
        event = ser.save()
        assert event.pk is not None

    def test_create_disallowed_file_type_succeeds(self, v2_attachment_event_type) -> None:
        """A PDF file when only 'image' is allowed succeeds on CREATE (validation is format-only)."""
        fc = _insert_filecontent(user=self.user, filename="notes.pdf")
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": str(fc.id)})
        assert ser.is_valid(), ser.errors
        event = ser.save()
        assert event.pk is not None

    def test_create_valid_owned_uuid_succeeds(self, v2_attachment_event_type) -> None:
        """A valid owned image UUID on CREATE saves successfully."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": str(ifc.id)})
        assert ser.is_valid(), ser.errors
        event = ser.save()
        assert event.pk is not None

    def test_create_returns_raw_uuid_not_proxy_url(self, v2_attachment_event_type) -> None:
        """After a successful CREATE the serialized event_details contain the raw UUID, not a proxy URL."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": str(ifc.id)})
        assert ser.is_valid(), ser.errors
        event = ser.save()
        # Re-serialize for reading
        read_ser = EventSerializer(instance=event, context=self._context())
        data = read_ser.data
        assert data["event_details"]["photo"] == str(ifc.id)
        assert "/api/v1.0/usercontent/" not in data["event_details"]["photo"]

    # -- UPDATE path --

    def test_update_unknown_uuid_succeeds(self, v2_attachment_event_type) -> None:
        """An unknown UUID on UPDATE succeeds (validation is format-only)."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": str(ifc.id)})
        assert ser.is_valid(), ser.errors
        event = ser.save()

        unknown_uuid = str(uuid.uuid4())
        update_ser = self._update_serializer(event, {"photo": unknown_uuid})
        assert update_ser.is_valid(), update_ser.errors
        updated_event = update_ser.save()
        assert updated_event.pk == event.pk

    def test_update_disallowed_file_type_succeeds(self, v2_attachment_event_type) -> None:
        """A PDF file when only 'image' is allowed succeeds on UPDATE (validation is format-only)."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": str(ifc.id)})
        assert ser.is_valid(), ser.errors
        event = ser.save()

        fc = _insert_filecontent(user=self.user, filename="notes.pdf")
        update_ser = self._update_serializer(event, {"photo": str(fc.id)})
        assert update_ser.is_valid(), update_ser.errors
        updated_event = update_ser.save()
        assert updated_event.pk == event.pk

    def test_update_valid_owned_uuid_succeeds(self, v2_attachment_event_type) -> None:
        """A valid owned image UUID on UPDATE saves successfully."""
        ifc1 = _insert_imagefilecontent(user=self.user, filename="photo1.jpg")
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": str(ifc1.id)})
        assert ser.is_valid(), ser.errors
        event = ser.save()

        ifc2 = _insert_imagefilecontent(user=self.user, filename="photo2.jpg")
        update_ser = self._update_serializer(event, {"photo": str(ifc2.id)})
        assert update_ser.is_valid(), update_ser.errors
        updated_event = update_ser.save()
        assert updated_event.pk == event.pk


# ---------------------------------------------------------------------------
# Metadata sidecar persistence tests (Part 3)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestV2AttachmentMetadataPersistence:
    """Verify that EventDetails.data stores the metadata sidecar on write."""

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _context(self, user=None) -> dict[str, Any]:
        if user is None:
            user = self.user
        request = _make_request(user)
        request.build_absolute_uri = lambda path: f"http://testserver{path}"
        return {"request": request}

    def _create_serializer(self, event_type_value: str, event_details: dict[str, Any]) -> Any:
        data = {
            "event_type": event_type_value,
            "title": "Test Event",
            "event_details": event_details,
        }
        return EventSerializer(data=data, context=self._context())

    def test_post_event_stores_attachment_placeholders_in_event_details_data(self, v2_attachment_event_type) -> None:
        """Creating an event with a UUID stores a {} placeholder in EventDetails.data["metadata"]."""
        photo_uuid = str(uuid.uuid4())
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": photo_uuid})
        assert ser.is_valid(), ser.errors
        event = ser.save()

        details = EventDetails.objects.filter(event=event).order_by("created_at").last()
        assert details is not None
        assert details.data["event_details"]["photo"] == photo_uuid
        assert "metadata" in details.data
        assert photo_uuid in details.data["metadata"]["attachments"]
        assert details.data["metadata"]["attachments"][photo_uuid] == {}

    def test_patch_event_removing_attachment_drops_placeholder(self, v2_attachment_event_type) -> None:
        """Updating event_details without the attachment UUID removes the metadata placeholder."""
        photo_uuid = str(uuid.uuid4())
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": photo_uuid})
        assert ser.is_valid(), ser.errors
        event = ser.save()

        # Patch: remove the attachment
        update_ser = EventSerializer(instance=event, data={"event_details": {"photo": ""}}, context=self._context())
        assert update_ser.is_valid(), update_ser.errors
        update_ser.save()

        details = EventDetails.objects.filter(event=event).order_by("created_at").last()
        assert details is not None
        assert "metadata" not in details.data

    def test_metadata_does_not_appear_in_event_details_output(self, v2_attachment_event_type) -> None:
        """The metadata sidecar must NOT appear inside event_details in the API response."""
        photo_uuid = str(uuid.uuid4())
        ser = self._create_serializer(v2_attachment_event_type.value, {"photo": photo_uuid})
        assert ser.is_valid(), ser.errors
        event = ser.save()

        read_ser = EventSerializer(instance=event, context=self._context())
        data = read_ser.data
        assert "metadata" not in data.get("event_details", {})

    def test_collect_attachment_uuids_v2_returns_uuids(self, v2_attachment_event_type) -> None:
        """_collect_attachment_uuids extracts valid UUID strings from attachment fields."""
        photo_uuid = str(uuid.uuid4())
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": photo_uuid})
        assert photo_uuid in result

    def test_collect_attachment_uuids_v2_ignores_empty_values(self, v2_attachment_event_type) -> None:
        """_collect_attachment_uuids skips None/empty attachment values."""
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": ""})
        assert result == set()

    def test_collect_attachment_uuids_v1_returns_empty(self, v1_event_type) -> None:
        """_collect_attachment_uuids returns empty set for V1 event types."""
        result = _collect_attachment_uuids(v1_event_type, {"photo": str(uuid.uuid4())})
        assert result == set()


# ---------------------------------------------------------------------------
# Read-path tests (raw UUID in event_details, metadata sidecar)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestV2AttachmentReadPath:
    """Verify the read path: raw UUID in event_details, hydrated metadata sidecar."""

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _serializer_with_context(self, event_type):
        request = _make_request(self.user)
        request.build_absolute_uri = lambda path: f"http://testserver{path}"
        event = _make_event(event_type, self.user)
        return EventDetailsSerializer(instance=event, context={"request": request})

    def _make_details(self, event, data: dict[str, Any]) -> EventDetails:
        return EventDetails.objects.create(event=event, data={"event_details": data})

    def _make_details_with_metadata(
        self, event, event_details_data: dict[str, Any], attachment_uuids: list[str]
    ) -> EventDetails:
        data: dict[str, Any] = {"event_details": event_details_data}
        if attachment_uuids:
            data["metadata"] = {"attachments": {u: {} for u in attachment_uuids}}
        return EventDetails.objects.create(event=event, data=data)

    def test_event_details_returns_raw_uuid_not_proxy_url(self, v2_attachment_event_type) -> None:
        """to_representation returns the raw stored UUID in event_details, not a proxy URL."""
        file_uuid = str(uuid.uuid4())
        ser = self._serializer_with_context(v2_attachment_event_type)
        details = self._make_details(ser.instance, {"photo": file_uuid})
        rep = ser.to_representation(details)
        assert rep["photo"] == file_uuid
        assert "/api/v1.0/usercontent/" not in rep["photo"]

    def test_null_value_unchanged(self, v2_attachment_event_type) -> None:
        ser = self._serializer_with_context(v2_attachment_event_type)
        details = self._make_details(ser.instance, {"photo": None})
        rep = ser.to_representation(details)
        assert rep["photo"] is None

    def test_absent_field_not_added(self, v2_attachment_event_type) -> None:
        ser = self._serializer_with_context(v2_attachment_event_type)
        details = self._make_details(ser.instance, {"comments": "hello"})
        rep = ser.to_representation(details)
        assert "photo" not in rep

    def test_no_request_context_leaves_uuid_unchanged(self, v2_attachment_event_type) -> None:
        event = _make_event(v2_attachment_event_type, self.user)
        ser = EventDetailsSerializer(instance=event, context={})
        file_uuid = str(uuid.uuid4())
        details = self._make_details(event, {"photo": file_uuid})
        rep = ser.to_representation(details)
        assert rep["photo"] == file_uuid

    def test_v1_event_type_unchanged(self, v1_event_type) -> None:
        event = _make_event(v1_event_type, self.user)
        request = _make_request(self.user)
        request.build_absolute_uri = lambda path: f"http://testserver{path}"
        ser = EventDetailsSerializer(instance=event, context={"request": request})
        file_uuid = str(uuid.uuid4())
        details = self._make_details(event, {"photo": file_uuid})
        rep = ser.to_representation(details)
        assert rep["photo"] == file_uuid

    def test_collection_nested_uuid_unchanged(self, v2_collection_attachment_event_type) -> None:
        file_uuid = str(uuid.uuid4())
        ser = self._serializer_with_context(v2_collection_attachment_event_type)
        details = self._make_details(ser.instance, {"arrests": [{"arrestee_photo": file_uuid}]})
        rep = ser.to_representation(details)
        # Raw UUID — no proxy URL in event_details
        assert rep["arrests"][0]["arrestee_photo"] == file_uuid

    def test_read_path_makes_no_gcs_calls(self, v2_attachment_event_type) -> None:
        """to_representation must not open any files from storage."""
        file_uuid = str(uuid.uuid4())
        ser = self._serializer_with_context(v2_attachment_event_type)
        details = self._make_details(ser.instance, {"photo": file_uuid})

        with MagicMock() as storage_open_mock:
            original_open = default_storage.open
            default_storage.open = storage_open_mock
            try:
                ser.to_representation(details)
            finally:
                default_storage.open = original_open

        storage_open_mock.assert_not_called()

    def test_broken_v2_schema_still_renders_stored_event(self, v2_empty_schema_event_type) -> None:
        """Read path: an event whose V2 event type has a broken schema still serializes."""
        file_uuid = str(uuid.uuid4())
        event = _make_event(v2_empty_schema_event_type, self.user)
        request = _make_request(self.user)
        request.build_absolute_uri = lambda path: f"http://testserver{path}"
        ser = EventDetailsSerializer(instance=event, context={"request": request})
        details = self._make_details(event, {"some_field": file_uuid})
        rep = ser.to_representation(details)
        assert rep["some_field"] == file_uuid

    # --- metadata sidecar hydration via EventSerializer ---

    def _event_context(self, user=None) -> dict[str, Any]:
        if user is None:
            user = self.user
        request = _make_request(user)
        request.build_absolute_uri = lambda path: f"http://testserver{path}"
        return {"request": request}

    def test_metadata_status_unknown_when_no_record(self, v2_attachment_event_type) -> None:
        """An attachment UUID with no session or DB row yields status=unknown."""
        file_uuid = str(uuid.uuid4())
        event = _make_event(v2_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"photo": file_uuid}, [file_uuid])

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        assert "metadata" in data
        attachment = data["metadata"]["attachments"][file_uuid]
        assert attachment["status"] == "unknown"
        assert "files" not in attachment

    def test_metadata_status_in_progress_with_live_session_only(self, v2_attachment_event_type) -> None:
        """A UUID with a live Redis session (no DB row) yields status=in_progress, no files key."""
        uid = str(uuid.uuid4())
        tenant_id = str(get_tenant_settings().id)
        upload_sessions.create(
            tenant_id,
            uid,
            storage_path=f"tenant/image_fileuploads/2024/1/1/{uid}/photo.jpg",
            filename="photo.jpg",
            size=1024,
            chunk_size=512,
            user_id=str(self.user.pk),
            is_image=True,
            file_content_id=uid,
        )
        event = _make_event(v2_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"photo": uid}, [uid])

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        attachment = data["metadata"]["attachments"][uid]
        assert attachment["status"] == "in_progress"
        assert "files" not in attachment
        assert "file_type" in attachment

    def test_metadata_status_complete_renders_files_original_and_file_type(self, v2_attachment_event_type) -> None:
        """A finalized ImageFileContent yields status=complete with files.original proxy URL."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        uid = str(ifc.id)
        event = _make_event(v2_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"photo": uid}, [uid])

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        attachment = data["metadata"]["attachments"][uid]
        assert attachment["status"] == "complete"
        assert attachment["file_type"] == "image"
        assert "files" in attachment
        assert f"/api/v1.0/usercontent/{uid}/" in attachment["files"]["original"]
        for rendition in ("icon", "thumbnail", "large", "xlarge"):
            assert rendition in attachment["files"]
            assert f"/api/v1.0/usercontent/{uid}/?rendition={rendition}" in attachment["files"][rendition]

    def test_metadata_file_type_for_non_image_complete_attachment(self, v2_no_filter_attachment_event_type) -> None:
        """A finalized PDF FileContent yields file_type=document with files.original."""
        fc = _insert_filecontent(user=self.user, filename="report.pdf")
        uid = str(fc.id)
        event = _make_event(v2_no_filter_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"doc": uid}, [uid])

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        attachment = data["metadata"]["attachments"][uid]
        assert attachment["status"] == "complete"
        assert attachment["file_type"] == "document"
        assert f"/api/v1.0/usercontent/{uid}/" in attachment["files"]["original"]
        assert set(attachment["files"].keys()) == {"original"}

    def test_metadata_hydration_skips_files_when_request_absent(self, v2_attachment_event_type) -> None:
        """Socket-emit (no request): complete attachment gets status+file_type but no files key."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        uid = str(ifc.id)
        event = _make_event(v2_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"photo": uid}, [uid])

        # No request in context (socket-emit path)
        read_ser = EventSerializer(instance=event, context={})
        data = read_ser.data
        assert "metadata" in data
        attachment = data["metadata"]["attachments"][uid]
        assert attachment["status"] == "complete"
        assert attachment["file_type"] == "image"
        assert "files" not in attachment

    def test_no_placeholders_means_no_metadata_key(self, v2_attachment_event_type) -> None:
        """When EventDetails has no metadata.attachments, the response omits metadata."""
        event = _make_event(v2_attachment_event_type, self.user)
        EventDetails.objects.create(event=event, data={"event_details": {"photo": ""}})

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        assert "metadata" not in data

    def test_hydration_uses_newest_details_row_on_prefetched_path(self, v2_attachment_event_type) -> None:
        """_hydrate_attachment_metadata must use the newest EventDetails row when prefetched.

        The Prefetch in the view uses order_by("-created_at") so event_details_set[0] is
        the newest row.  This test verifies that contract by constructing two rows directly
        via the ORM, setting event_details_set on the instance to simulate the prefetch
        (newest first), and confirming that the metadata from the newer row is hydrated.

        It also verifies the inverse: if the list were ordered oldest-first (the pre-fix
        state), the wrong row would be selected and metadata would be absent.
        """
        photo_uuid = str(uuid.uuid4())
        event = _make_event(v2_attachment_event_type, self.user)

        # Older row: no attachment metadata.
        older_details = EventDetails.objects.create(
            event=event,
            data={"event_details": {"photo": ""}},
        )
        # Newer row: has the attachment placeholder.
        newer_details = EventDetails.objects.create(
            event=event,
            data={
                "event_details": {"photo": photo_uuid},
                "metadata": {"attachments": {photo_uuid: {}}},
            },
        )

        # Positive case: newest-first (matches the -created_at Prefetch ordering).
        # event_details_set[0] == newer_details → metadata IS hydrated.
        event.event_details_set = [newer_details, older_details]
        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        assert "metadata" in data, "Expected metadata from the newer row to be hydrated"
        assert photo_uuid in data["metadata"]["attachments"]

        # Negative case: oldest-first (the pre-fix ordering).
        # event_details_set[0] == older_details → no attachment placeholder → no metadata key.
        event.event_details_set = [older_details, newer_details]
        read_ser2 = EventSerializer(instance=event, context=self._event_context())
        data2 = read_ser2.data
        assert (
            "metadata" not in data2
        ), "With oldest-first ordering, the wrong row is read and metadata should be absent"

    def test_webp_stored_as_filecontent_emits_no_renditions(self, v2_attachment_event_type) -> None:
        """A .webp file stored as FileContent (not ImageFileContent) must NOT emit rendition URLs.

        webp is in image_extensions (so file_type="image") but NOT in imagefile_extensions,
        so the upload pipeline stores it as plain FileContent.  The download view checks
        isinstance(instance, ImageFileContent) before serving renditions, so any rendition
        URL for a FileContent row always 404s.  The sidecar must only include "original".
        """
        fc = _insert_filecontent(user=self.user, filename="photo.webp")
        uid = str(fc.id)
        event = _make_event(v2_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"photo": uid}, [uid])

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        attachment = data["metadata"]["attachments"][uid]
        assert attachment["status"] == "complete"
        # file_type is still "image" — that classification is display-only
        assert attachment["file_type"] == "image"
        assert "files" in attachment
        assert f"/api/v1.0/usercontent/{uid}/" in attachment["files"]["original"]
        # No rendition keys — the row is FileContent, not ImageFileContent
        assert set(attachment["files"].keys()) == {"original"}

    def test_heic_stored_as_filecontent_emits_no_renditions(self, v2_attachment_event_type) -> None:
        """A .heic file stored as FileContent must NOT emit rendition URLs."""
        fc = _insert_filecontent(user=self.user, filename="photo.heic")
        uid = str(fc.id)
        event = _make_event(v2_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"photo": uid}, [uid])

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        attachment = data["metadata"]["attachments"][uid]
        assert attachment["status"] == "complete"
        assert attachment["file_type"] == "image"
        assert set(attachment["files"].keys()) == {"original"}

    def test_bmp_stored_as_filecontent_emits_no_renditions(self, v2_attachment_event_type) -> None:
        """A .bmp file stored as FileContent must NOT emit rendition URLs."""
        fc = _insert_filecontent(user=self.user, filename="photo.bmp")
        uid = str(fc.id)
        event = _make_event(v2_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"photo": uid}, [uid])

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        attachment = data["metadata"]["attachments"][uid]
        assert attachment["status"] == "complete"
        assert attachment["file_type"] == "image"
        assert set(attachment["files"].keys()) == {"original"}

    def test_jpg_stored_as_imagefilecontent_emits_renditions(self, v2_attachment_event_type) -> None:
        """A .jpg file stored as ImageFileContent DOES emit rendition URLs.

        Positive control: confirms that the has_renditions gate permits rendition emission
        for files that actually are ImageFileContent instances.
        """
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        uid = str(ifc.id)
        event = _make_event(v2_attachment_event_type, self.user)
        self._make_details_with_metadata(event, {"photo": uid}, [uid])

        read_ser = EventSerializer(instance=event, context=self._event_context())
        data = read_ser.data
        attachment = data["metadata"]["attachments"][uid]
        assert attachment["status"] == "complete"
        assert attachment["file_type"] == "image"
        assert "files" in attachment
        for rendition in ("icon", "thumbnail", "large", "xlarge"):
            assert rendition in attachment["files"], f"Expected rendition key '{rendition}' missing"
            assert f"?rendition={rendition}" in attachment["files"][rendition]


# ---------------------------------------------------------------------------
# Performance guard: get_rendered_schema must NOT be called on either path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRawSchemaUsedNotRendered:
    """Ensure the read and write paths use get_raw_schema, not get_rendered_schema.

    get_rendered_schema dereferences $ref URLs and is expensive (HTTP + registry
    build). Using get_raw_schema for slot discovery is sufficient and avoids that
    cost even when the event type has no attachment slots.
    """

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _serializer_with_context(self, event_type):
        request = _make_request(self.user)
        request.build_absolute_uri = lambda path: f"http://testserver{path}"
        event = _make_event(event_type, self.user)
        return EventDetailsSerializer(instance=event, context={"request": request})

    def test_read_path_does_not_call_get_rendered_schema(self, v2_attachment_event_type) -> None:
        """to_representation must not invoke get_rendered_schema."""
        file_uuid = str(uuid.uuid4())
        ser = self._serializer_with_context(v2_attachment_event_type)
        details = EventDetails.objects.create(event=ser.instance, data={"event_details": {"photo": file_uuid}})

        with patch.object(
            EventTypeSchemaService,
            "get_rendered_schema",
            side_effect=AssertionError("get_rendered_schema must not be called on the read path"),
        ):
            rep = ser.to_representation(details)

        # Raw UUID is returned unchanged
        assert rep["photo"] == file_uuid

    def test_write_path_does_not_call_get_rendered_schema(self, v2_attachment_event_type) -> None:
        """_to_internal_value_inner must not invoke get_rendered_schema."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        ser = self._serializer_with_context(v2_attachment_event_type)

        with patch.object(
            EventTypeSchemaService,
            "get_rendered_schema",
            side_effect=AssertionError("get_rendered_schema must not be called on the write path"),
        ):
            result = ser._to_internal_value_inner(ser.instance, {"photo": str(ifc.id)})

        assert result["photo"] == str(ifc.id)

    def test_write_succeeds_for_v2_event_with_no_attachment_fields_when_renderer_would_fail(
        self, v2_no_attachment_event_type
    ) -> None:
        """A V2 event with no attachment fields must succeed even when get_rendered_schema would fail."""
        ser = self._serializer_with_context(v2_no_attachment_event_type)

        with patch.object(
            EventTypeSchemaService,
            "get_rendered_schema",
            side_effect=AssertionError("get_rendered_schema must not be called"),
        ):
            result = ser._to_internal_value_inner(ser.instance, {"notes": "hello"})

        assert result["notes"] == "hello"

    def test_unparseable_raw_schema_raises_validation_error_on_write(self, event_category) -> None:
        """A V2 event type with unparseable raw JSON schema raises ValidationError (400) on write."""
        event_type = EventTypeFactory.create(
            category=event_category,
            value="v2_bad_json_write_test",
            schema="{not json",
            version=EventType.VersionChoices.VERSION_2,
        )
        request = _make_request(self.user)
        event = _make_event(event_type, self.user)
        ser = EventDetailsSerializer(instance=event, context={"request": request})

        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(event, {"some_field": "value"})

        assert "unparseable V2 schema" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# Security tests — attachment metadata must respect the event permission gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAttachmentMetadataPermissionGate:
    """Verify that attachment UUIDs and proxy URLs are never exposed to unpermitted users.

    The EventSerializer._to_representation early-return (lines 1074-1075) emits only
    ``{id, serial_number}`` for users lacking category_read permission.  The metadata
    hydration call sits after that gate, so it is never reached for unpermitted requests.
    """

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _make_request_for_user(self, user):
        request = _make_request(user)
        request.build_absolute_uri = lambda path: f"http://testserver{path}"
        return request

    def _context_for_user(self, user) -> dict[str, Any]:
        return {"request": self._make_request_for_user(user)}

    def test_get_event_without_category_read_permission_excludes_metadata(self, v2_attachment_event_type) -> None:
        """A user without category_read sees only {id, serial_number}; metadata/event_details absent."""
        photo_uuid = str(uuid.uuid4())
        event = _make_event(v2_attachment_event_type, self.user)
        details_data: dict[str, Any] = {"event_details": {"photo": photo_uuid}}
        details_data["metadata"] = {"attachments": {photo_uuid: {}}}
        EventDetails.objects.create(event=event, data=details_data)

        # Create a user with NO permissions at all
        unpermitted = User.objects.create_user(
            "sec-no-perm",
            "sec-no-perm@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=False,
        )
        read_ser = EventSerializer(instance=event, context=self._context_for_user(unpermitted))
        data = read_ser.data

        # Only id and serial_number should be present
        assert set(data.keys()) == {"id", "serial_number"}
        assert "metadata" not in data
        assert "event_details" not in data
        # No usercontent UUID or URL anywhere in the response
        assert photo_uuid not in str(data)
        assert "usercontent" not in str(data)

    def test_get_event_with_category_read_permission_includes_metadata(self, v2_attachment_event_type) -> None:
        """Prove the permission gate admits the metadata sidecar for a permitted user.

        self.user is admin_user (Django superuser), so has_perm returns True for all
        category-read checks.  A random UUID with no FileContent row and no Redis session
        resolves to exactly {"status": "unknown"} via get_attachment_info.  The raw UUID
        must be retained in event_details (not replaced with a proxy URL) per the
        read-path behavior in ERA-13273.
        """
        photo_uuid = str(uuid.uuid4())
        event = _make_event(v2_attachment_event_type, self.user)
        details_data: dict[str, Any] = {"event_details": {"photo": photo_uuid}}
        details_data["metadata"] = {"attachments": {photo_uuid: {}}}
        EventDetails.objects.create(event=event, data=details_data)

        read_ser = EventSerializer(instance=event, context=self._context_for_user(self.user))
        data = read_ser.data

        # The metadata sidecar must be present and fully hydrated
        assert "metadata" in data
        assert photo_uuid in data["metadata"]["attachments"]
        assert data["metadata"]["attachments"][photo_uuid] == {"status": "unknown"}
        # Raw UUID retained in event_details — no proxy URL substitution on read
        assert data["event_details"]["photo"] == photo_uuid

    def test_attachment_proxy_urls_not_leaked_to_unpermitted_user(self, v2_attachment_event_type) -> None:
        """No usercontent/<uuid>/ URL appears anywhere in the unpermitted user's response."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        uid = str(ifc.id)
        event = _make_event(v2_attachment_event_type, self.user)
        details_data: dict[str, Any] = {"event_details": {"photo": uid}}
        details_data["metadata"] = {"attachments": {uid: {}}}
        EventDetails.objects.create(event=event, data=details_data)

        unpermitted = User.objects.create_user(
            "sec-no-url",
            "sec-no-url@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=False,
        )
        read_ser = EventSerializer(instance=event, context=self._context_for_user(unpermitted))
        data = read_ser.data

        response_str = str(data)
        assert f"usercontent/{uid}" not in response_str
        assert "/api/v1.0/usercontent/" not in response_str

    def test_list_events_excludes_events_user_cannot_read(self, v2_attachment_event_type) -> None:
        """EventPermissionsFilter excludes events whose category the user cannot read.

        Exercises the real EventPermissionsFilter.filter_queryset machinery (no mocking
        of has_perm).  A non-staff user with no permissions receives queryset.none()
        because no event category passes the permission check, so the event carrying
        attachment placeholders is absent from the result.  admin_user (superuser) sees
        the same event, proving the filter discriminates on permission rather than
        always returning empty.
        """
        photo_uuid = str(uuid.uuid4())
        event = _make_event(v2_attachment_event_type, self.user)
        details_data: dict[str, Any] = {"event_details": {"photo": photo_uuid}}
        details_data["metadata"] = {"attachments": {photo_uuid: {}}}
        EventDetails.objects.create(event=event, data=details_data)

        # Build an unpermitted user with no staff flag and no explicit permissions.
        unpermitted = User.objects.create_user(
            "sec-filter-no-perm",
            "sec-filter-no-perm@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=False,
        )

        factory = APIRequestFactory()

        # Negative case: unpermitted user — event must NOT appear in the filtered queryset.
        raw_unpermitted_request = factory.get("/")
        unpermitted_request = Request(raw_unpermitted_request)
        unpermitted_request.user = unpermitted
        result_unpermitted = EventPermissionsFilter().filter_queryset(
            unpermitted_request, Event.objects.all(), view=None
        )
        assert not result_unpermitted.filter(pk=event.pk).exists()

        # Positive control: admin_user (superuser) — event IS present.
        raw_admin_request = factory.get("/")
        admin_request = Request(raw_admin_request)
        admin_request.user = self.user
        result_admin = EventPermissionsFilter().filter_queryset(admin_request, Event.objects.all(), view=None)
        assert result_admin.filter(pk=event.pk).exists()
