"""Tests for V2 event-type attachment field handling in EventDetailsSerializer (ERA-13420).

Attachment fields store arrays of objects with shape ``{"uploadId": "<uuid>"}``.
A plain UUID string (legacy shape), an empty string, and non-list values are all
rejected.  Null / absent values and empty lists are accepted.

Write path: any array of well-formed ``{"uploadId": "<uuid>"}`` objects passes.
Validation is format-only — ownership, existence, and file type are NOT checked
at write time.  Extra keys on an item object are rejected (mirrors
``unevaluatedProperties: false``).

Metadata sidecar: EventDetails.data["metadata"]["attachments"] stores a ``{}``
placeholder for each ``uploadId`` value present across all attachment slots at
write time.

minItems / maxItems bounds from the field's JSON schema definition are enforced:
- ``None`` (field absent) → always accepted regardless of minItems.
- Any list (empty or non-empty) shorter than minItems → rejected.
- Any list longer than maxItems → rejected.  ``maxItems: 0`` with a non-empty
  array → rejected.

Collection-nested attachment bounds: extracted from the field's JSON schema
definition inside the collection's items.properties sub-tree (via
get_field_schema_from_prop_path) and enforced identically to flat fields.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from activity.models import Event, EventDetails, EventType
from activity.schemas.eventtype_service import SchemaResult
from activity.serializers.event_details import (
    EventDetailsSerializer,
    _collect_attachment_uuids,
)
from factories import EventCategoryFactory, EventTypeFactory

_V2_DRAFT = "https://json-schema.org/draft/2020-12/schema"


# ---------------------------------------------------------------------------
# Schema builders
# ---------------------------------------------------------------------------


def _attachment_field_json_def(
    min_items: int | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    """Build the JSON schema definition for an attachment field (stored in EventType schema)."""
    defn: dict[str, Any] = {
        "deprecated": False,
        "title": "Photo",
        "type": "array",
        "uniqueItems": True,
        "items": {
            "properties": {"uploadId": {"format": "uuid", "type": "string"}},
            "required": ["uploadId"],
            "type": "object",
            "unevaluatedProperties": False,
        },
    }
    if min_items is not None:
        defn["minItems"] = min_items
    if max_items is not None:
        defn["maxItems"] = max_items
    return defn


def _attachment_event_type_schema(
    field_name: str = "photo",
    allowable_file_types: list[str] | None = None,
    min_items: int | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    """Build a minimal V2 schema with a single top-level ATTACHMENT field."""
    if allowable_file_types is None:
        allowable_file_types = []
    return {
        "json": {
            "$schema": _V2_DRAFT,
            "type": "object",
            "properties": {
                field_name: _attachment_field_json_def(min_items=min_items, max_items=max_items),
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
    min_items: int | None = None,
    max_items: int | None = None,
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
                            attachment_field: _attachment_field_json_def(min_items=min_items, max_items=max_items),
                        },
                        "required": [],
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
                    "leftColumn": [f"{collection_name}.{attachment_field}"],
                    "rightColumn": [],
                    "type": "COLLECTION",
                    "parent": "section-1",
                },
                f"{collection_name}.{attachment_field}": {
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
    return EventCategoryFactory.create(value="arr_attach_test_cat")


@pytest.fixture
def v2_attachment_event_type(event_category):
    return EventTypeFactory.create(
        category=event_category,
        value="v2_arr_attachment_test",
        schema=json.dumps(_attachment_event_type_schema("photo", ["image"])),
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_attachment_min2_event_type(event_category):
    return EventTypeFactory.create(
        category=event_category,
        value="v2_arr_attach_min2",
        schema=json.dumps(_attachment_event_type_schema("photo", [], min_items=2)),
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_attachment_max1_event_type(event_category):
    return EventTypeFactory.create(
        category=event_category,
        value="v2_arr_attach_max1",
        schema=json.dumps(_attachment_event_type_schema("photo", [], max_items=1)),
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_attachment_max0_event_type(event_category):
    return EventTypeFactory.create(
        category=event_category,
        value="v2_arr_attach_max0",
        schema=json.dumps(_attachment_event_type_schema("photo", [], max_items=0)),
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_collection_attachment_event_type(event_category):
    return EventTypeFactory.create(
        category=event_category,
        value="v2_arr_collection_attachment",
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
        value="v1_arr_with_photo",
        schema=v1_schema,
        version=EventType.VersionChoices.VERSION_1,
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
    req = factory.get("/")
    req.user = user
    return req


def _upload_obj(uid: str | None = None) -> dict[str, str]:
    """Return a well-formed attachment item object."""
    return {"uploadId": uid if uid is not None else str(uuid.uuid4())}


# ---------------------------------------------------------------------------
# Unit tests for extract_attachment_slots bounds extraction
# ---------------------------------------------------------------------------


class TestExtractAttachmentSlotsBounds:
    """extract_attachment_slots populates min_items / max_items from json.properties."""

    def _result(self, schema: dict[str, Any]) -> SchemaResult:
        return SchemaResult(event_type_value="test", schema=schema)

    def test_flat_field_with_no_bounds_returns_none(self) -> None:
        """A flat attachment field with no minItems/maxItems yields None bounds."""
        schema = _attachment_event_type_schema("photo")
        slots = self._result(schema).extract_attachment_slots()
        assert slots["photo"].field.min_items is None
        assert slots["photo"].field.max_items is None

    def test_flat_field_with_min_items_extracts_value(self) -> None:
        """minItems is extracted when present on the json definition."""
        schema = _attachment_event_type_schema("photo", min_items=1)
        slots = self._result(schema).extract_attachment_slots()
        assert slots["photo"].field.min_items == 1

    def test_flat_field_with_max_items_extracts_value(self) -> None:
        """maxItems is extracted when present on the json definition."""
        schema = _attachment_event_type_schema("photo", max_items=5)
        slots = self._result(schema).extract_attachment_slots()
        assert slots["photo"].field.max_items == 5

    def test_flat_field_with_min_and_max_items_extracted(self) -> None:
        """Both minItems and maxItems are extracted when both are present."""
        schema = _attachment_event_type_schema("photo", min_items=1, max_items=3)
        slots = self._result(schema).extract_attachment_slots()
        assert slots["photo"].field.min_items == 1
        assert slots["photo"].field.max_items == 3

    def test_collection_nested_attachment_no_bounds_returns_none(self) -> None:
        """Collection-nested attachment field with no minItems/maxItems yields None bounds."""
        schema = _collection_attachment_schema("arrests", "arrestee_photo")
        slots = self._result(schema).extract_attachment_slots()
        assert slots["arrests.arrestee_photo"].field.min_items is None
        assert slots["arrests.arrestee_photo"].field.max_items is None

    def test_collection_nested_attachment_min_items_extracted(self) -> None:
        """minItems on a collection-nested attachment field is extracted correctly."""
        schema = _collection_attachment_schema("arrests", "arrestee_photo", min_items=2)
        slots = self._result(schema).extract_attachment_slots()
        assert slots["arrests.arrestee_photo"].field.min_items == 2

    def test_collection_nested_attachment_max_items_extracted(self) -> None:
        """maxItems on a collection-nested attachment field is extracted correctly."""
        schema = _collection_attachment_schema("arrests", "arrestee_photo", max_items=3)
        slots = self._result(schema).extract_attachment_slots()
        assert slots["arrests.arrestee_photo"].field.max_items == 3

    def test_collection_nested_attachment_min_and_max_items_extracted(self) -> None:
        """Both minItems and maxItems on a collection-nested attachment field are extracted."""
        schema = _collection_attachment_schema("arrests", "arrestee_photo", min_items=1, max_items=4)
        slots = self._result(schema).extract_attachment_slots()
        assert slots["arrests.arrestee_photo"].field.min_items == 1
        assert slots["arrests.arrestee_photo"].field.max_items == 4

    def test_json_properties_key_missing_gives_none_bounds(self) -> None:
        """When json.properties is missing entirely, bounds default to None."""
        schema = {
            "json": {"$schema": _V2_DRAFT, "type": "object", "required": []},
            "ui": {
                "fields": {"photo": {"allowableFileTypes": [], "type": "ATTACHMENT", "parent": "section-1"}},
                "headers": {},
                "order": [],
                "sections": {},
            },
        }
        slots = self._result(schema).extract_attachment_slots()
        assert slots["photo"].field.min_items is None
        assert slots["photo"].field.max_items is None

    def test_json_property_not_a_dict_gives_none_bounds(self) -> None:
        """When json.properties[field] is not a dict, bounds default to None without error."""
        schema = {
            "json": {
                "$schema": _V2_DRAFT,
                "type": "object",
                "properties": {"photo": "not-a-dict"},
                "required": [],
            },
            "ui": {
                "fields": {"photo": {"allowableFileTypes": [], "type": "ATTACHMENT", "parent": "section-1"}},
                "headers": {},
                "order": [],
                "sections": {},
            },
        }
        slots = self._result(schema).extract_attachment_slots()
        assert slots["photo"].field.min_items is None
        assert slots["photo"].field.max_items is None

    def _schema_with_raw_bounds(self, min_items: Any, max_items: Any) -> dict[str, Any]:
        """Build a schema where minItems/maxItems are set to arbitrary raw values."""
        defn = _attachment_field_json_def()
        defn["minItems"] = min_items
        defn["maxItems"] = max_items
        return {
            "json": {
                "$schema": _V2_DRAFT,
                "type": "object",
                "properties": {"photo": defn},
                "required": [],
            },
            "ui": {
                "fields": {"photo": {"allowableFileTypes": [], "type": "ATTACHMENT", "parent": "section-1"}},
                "headers": {},
                "order": ["section-1"],
                "sections": {
                    "section-1": {
                        "columns": 1,
                        "isActive": True,
                        "label": "",
                        "leftColumn": [{"name": "photo", "type": "field"}],
                        "rightColumn": [],
                    }
                },
            },
        }

    def test_bool_true_min_items_rejected_as_none(self) -> None:
        """minItems: true is rejected (bool is a subclass of int; we must guard against it)."""
        slots = self._result(self._schema_with_raw_bounds(True, None)).extract_attachment_slots()
        assert slots["photo"].field.min_items is None

    def test_bool_false_max_items_rejected_as_none(self) -> None:
        """maxItems: false is rejected (bool is a subclass of int; we must guard against it)."""
        slots = self._result(self._schema_with_raw_bounds(None, False)).extract_attachment_slots()
        assert slots["photo"].field.max_items is None

    def test_negative_min_items_rejected_as_none(self) -> None:
        """Negative minItems is rejected; only non-negative ints are valid bounds."""
        slots = self._result(self._schema_with_raw_bounds(-1, None)).extract_attachment_slots()
        assert slots["photo"].field.min_items is None

    def test_negative_max_items_rejected_as_none(self) -> None:
        """Negative maxItems is rejected; only non-negative ints are valid bounds."""
        slots = self._result(self._schema_with_raw_bounds(None, -5)).extract_attachment_slots()
        assert slots["photo"].field.max_items is None

    def test_zero_min_items_accepted(self) -> None:
        """minItems: 0 is a valid non-negative bound and must be extracted as 0."""
        slots = self._result(self._schema_with_raw_bounds(0, None)).extract_attachment_slots()
        assert slots["photo"].field.min_items == 0

    def test_zero_max_items_accepted(self) -> None:
        """maxItems: 0 is a valid non-negative bound and must be extracted as 0."""
        slots = self._result(self._schema_with_raw_bounds(None, 0)).extract_attachment_slots()
        assert slots["photo"].field.max_items == 0


# ---------------------------------------------------------------------------
# Unit tests for _validate_attachment_value (pure logic, no DB)
# ---------------------------------------------------------------------------


class TestValidateAttachmentValue:
    """Direct unit tests for EventDetailsSerializer._validate_attachment_value."""

    def _ser(self) -> EventDetailsSerializer:
        """Return an unbound serializer (no instance needed for pure validation)."""
        return EventDetailsSerializer.__new__(EventDetailsSerializer)

    # -- Accepted values --

    def test_none_accepted(self) -> None:
        """None is accepted regardless of minItems (optionality governed by schema required list)."""
        assert self._ser()._validate_attachment_value(None) == []

    def test_none_accepted_even_when_min_items_is_1(self) -> None:
        """None is accepted even when minItems >= 1 (absence ≠ empty)."""
        assert self._ser()._validate_attachment_value(None, min_items=1) == []

    def test_empty_list_accepted_with_no_bounds(self) -> None:
        """An empty list is accepted when no bounds are set."""
        assert self._ser()._validate_attachment_value([]) == []

    def test_empty_list_accepted_when_min_items_is_0(self) -> None:
        """An empty list is accepted when minItems is 0."""
        assert self._ser()._validate_attachment_value([], min_items=0) == []

    def test_single_object_item_accepted(self) -> None:
        """A single-element array containing a valid upload object is accepted."""
        assert self._ser()._validate_attachment_value([_upload_obj()]) == []

    def test_multi_object_array_accepted(self) -> None:
        """A multi-element array of distinct valid upload objects is accepted."""
        items = [_upload_obj(), _upload_obj(), _upload_obj()]
        assert self._ser()._validate_attachment_value(items) == []

    def test_unknown_uuid_accepted_format_only(self) -> None:
        """A well-formed UUID with no matching DB row passes (format-only validation)."""
        assert self._ser()._validate_attachment_value([_upload_obj()]) == []

    # -- Rejected non-list values --

    @pytest.mark.parametrize(
        "bad_value",
        [
            str(uuid.uuid4()),  # bare UUID string (legacy shape)
            "",  # empty string
            "not-a-uuid",
            12345,
            {"uploadId": str(uuid.uuid4())},  # bare dict (not wrapped in a list)
            True,
        ],
        ids=["bare_uuid_string", "empty_string", "non_uuid_string", "int", "dict", "bool"],
    )
    def test_non_list_value_rejected(self, bad_value: Any) -> None:
        """Any non-list value (including a bare UUID string) is rejected with 'Expected an array'."""
        errors = self._ser()._validate_attachment_value(bad_value)
        assert errors
        assert "Expected an array" in errors[0]

    # -- Per-item validation: item must be a dict --

    def test_non_dict_item_rejected(self) -> None:
        """A non-dict item (e.g. plain UUID string) in the array is rejected."""
        errors = self._ser()._validate_attachment_value([str(uuid.uuid4())])
        assert errors
        assert "index 0" in errors[0]

    def test_integer_item_rejected(self) -> None:
        """An integer item in the array is rejected."""
        errors = self._ser()._validate_attachment_value([42])
        assert errors
        assert "index 0" in errors[0]

    def test_none_item_rejected(self) -> None:
        """A None item in the array is rejected."""
        errors = self._ser()._validate_attachment_value([None])
        assert errors
        assert "index 0" in errors[0]

    # -- Per-item validation: missing uploadId --

    def test_item_missing_upload_id_rejected(self) -> None:
        """An item dict without the 'uploadId' key is rejected."""
        errors = self._ser()._validate_attachment_value([{}])
        assert errors
        assert "index 0" in errors[0]

    # -- Per-item validation: extra keys rejected --

    def test_item_with_extra_key_rejected(self) -> None:
        """An item dict with an extra key besides 'uploadId' is rejected."""
        uid = str(uuid.uuid4())
        errors = self._ser()._validate_attachment_value([{"uploadId": uid, "extra": "oops"}])
        assert errors
        assert "index 0" in errors[0]

    def test_item_with_only_extra_key_rejected(self) -> None:
        """An item dict with no 'uploadId' but a different key is rejected."""
        errors = self._ser()._validate_attachment_value([{"id": str(uuid.uuid4())}])
        assert errors
        assert "index 0" in errors[0]

    # -- Per-item validation: uploadId value must be a valid UUID string --

    def test_upload_id_not_a_string_rejected(self) -> None:
        """uploadId that is not a string is rejected."""
        errors = self._ser()._validate_attachment_value([{"uploadId": 12345}])
        assert errors
        assert "index 0" in errors[0]
        assert "uploadId" in errors[0]

    def test_upload_id_empty_string_rejected(self) -> None:
        """uploadId that is an empty string is rejected."""
        errors = self._ser()._validate_attachment_value([{"uploadId": ""}])
        assert errors
        assert "index 0" in errors[0]
        assert "uploadId" in errors[0]

    def test_upload_id_malformed_uuid_rejected(self) -> None:
        """uploadId that is not a valid UUID string is rejected, naming key and value."""
        errors = self._ser()._validate_attachment_value([{"uploadId": "not-a-uuid"}])
        assert errors
        assert "index 0" in errors[0]
        assert "uploadId" in errors[0]
        assert "not-a-uuid" in errors[0]

    def test_multiple_bad_items_each_reported(self) -> None:
        """Each bad item in a multi-item array produces a separate error."""
        errors = self._ser()._validate_attachment_value([{"uploadId": "bad1"}, {"uploadId": "bad2"}])
        assert len(errors) == 2
        assert "index 0" in errors[0]
        assert "index 1" in errors[1]

    def test_mixed_good_and_bad_items_reports_bad_only(self) -> None:
        """Only bad items produce errors; valid upload objects are accepted silently."""
        errors = self._ser()._validate_attachment_value([_upload_obj(), {"uploadId": "not-a-uuid"}])
        assert len(errors) == 1
        assert "index 1" in errors[0]

    # -- Duplicate uploadId detection --

    def test_duplicate_upload_ids_rejected(self) -> None:
        """Duplicate uploadId values in a single array are rejected (uniqueItems: true)."""
        uid = str(uuid.uuid4())
        errors = self._ser()._validate_attachment_value([{"uploadId": uid}, {"uploadId": uid}])
        assert errors
        assert "duplicate" in errors[0].lower()

    def test_distinct_upload_ids_not_reported_as_duplicates(self) -> None:
        """Two distinct uploadId values do not trigger the duplicate check."""
        assert self._ser()._validate_attachment_value([_upload_obj(), _upload_obj()]) == []

    # -- minItems enforcement --

    def test_empty_list_rejected_when_min_items_is_1(self) -> None:
        """An empty list fails when minItems >= 1."""
        errors = self._ser()._validate_attachment_value([], min_items=1)
        assert errors
        assert "at least 1" in errors[0]

    def test_non_empty_list_below_min_items_rejected(self) -> None:
        """A non-empty list shorter than minItems is also rejected."""
        errors = self._ser()._validate_attachment_value([_upload_obj()], min_items=3)
        assert errors
        assert "at least 3" in errors[0]

    def test_list_meeting_min_items_accepted(self) -> None:
        """A list with exactly minItems elements is accepted."""
        items = [_upload_obj(), _upload_obj()]
        assert self._ser()._validate_attachment_value(items, min_items=2) == []

    def test_list_exceeding_min_items_accepted(self) -> None:
        """A list with more elements than minItems is accepted."""
        items = [_upload_obj(), _upload_obj(), _upload_obj()]
        assert self._ser()._validate_attachment_value(items, min_items=2) == []

    # -- maxItems enforcement --

    def test_list_exceeding_max_items_rejected(self) -> None:
        """A list whose length exceeds maxItems is rejected."""
        items = [_upload_obj(), _upload_obj()]
        errors = self._ser()._validate_attachment_value(items, max_items=1)
        assert errors
        assert "at most 1" in errors[0]

    def test_max_items_0_with_non_empty_array_rejected(self) -> None:
        """maxItems: 0 means no items are allowed; a non-empty array fails."""
        errors = self._ser()._validate_attachment_value([_upload_obj()], max_items=0)
        assert errors
        assert "at most 0" in errors[0]

    def test_list_within_max_items_accepted(self) -> None:
        """A list with exactly maxItems elements is accepted."""
        assert self._ser()._validate_attachment_value([_upload_obj()], max_items=1) == []

    def test_empty_list_with_max_items_0_accepted(self) -> None:
        """An empty list satisfies maxItems: 0 (nothing to check)."""
        assert self._ser()._validate_attachment_value([], max_items=0) == []


# ---------------------------------------------------------------------------
# Integration tests: _to_internal_value_inner through EventDetailsSerializer
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Normalization tests: non-canonical uploadId forms are coerced to canonical
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUploadIdNormalization:
    """Accepted uploadId values are stored in canonical lowercase UUID form.

    uuid.UUID() can parse many equivalent representations (uppercase, urn:uuid:,
    braced, non-hyphenated hex).  We normalize on write so downstream URL building
    and sidecar keying always see the canonical ``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx``
    form.  Duplicate detection already normalizes before comparing, so two differently
    formatted spellings of the same UUID are still rejected as duplicates.
    """

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _serializer(self, event_type):
        req = _make_request(self.user)
        event = _make_event(event_type, self.user)
        return EventDetailsSerializer(instance=event, context={"request": req})

    def _canonical(self, uid: str) -> str:
        return str(uuid.UUID(uid))

    def test_uppercase_upload_id_normalized_to_lowercase(self, v2_attachment_event_type) -> None:
        """An uppercase UUID uploadId is accepted and stored in canonical lowercase form."""
        uid = str(uuid.uuid4()).upper()
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": [{"uploadId": uid}]})
        assert result["photo"][0]["uploadId"] == self._canonical(uid)
        assert result["photo"][0]["uploadId"] == result["photo"][0]["uploadId"].lower()

    def test_urn_upload_id_normalized_to_canonical(self, v2_attachment_event_type) -> None:
        """A urn:uuid:<...> uploadId is accepted and stored in canonical form."""
        uid = str(uuid.uuid4())
        urn_form = f"urn:uuid:{uid}"
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": [{"uploadId": urn_form}]})
        assert result["photo"][0]["uploadId"] == uid

    def test_non_hyphenated_hex_upload_id_normalized(self, v2_attachment_event_type) -> None:
        """A 32-character non-hyphenated hex uploadId is accepted and stored in canonical form."""
        uid = str(uuid.uuid4())
        hex_form = uid.replace("-", "")
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": [{"uploadId": hex_form}]})
        assert result["photo"][0]["uploadId"] == uid

    def test_sidecar_keyed_by_canonical_form_for_uppercase_input(self, v2_attachment_event_type) -> None:
        """_collect_attachment_uuids returns the canonical lowercase form for an uppercase uploadId."""
        uid = str(uuid.uuid4())
        uppercase_uid = uid.upper()
        from activity.serializers.event_details import _collect_attachment_uuids

        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": [{"uploadId": uppercase_uid}]})
        assert uid in result
        assert uppercase_uid not in result

    def test_malformed_upload_id_still_rejected(self, v2_attachment_event_type) -> None:
        """A truly malformed uploadId string is still rejected even with normalization in place."""
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [{"uploadId": "not-a-uuid"}]})
        assert "photo" in exc_info.value.detail

    def test_same_uuid_in_different_cases_detected_as_duplicate(self, v2_attachment_event_type) -> None:
        """Two items with the same UUID in different cases (upper/lower) are rejected as duplicates."""
        uid_lower = str(uuid.uuid4())
        uid_upper = uid_lower.upper()
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [{"uploadId": uid_lower}, {"uploadId": uid_upper}]})
        assert "photo" in exc_info.value.detail


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestV2AttachmentArrayWriteValidation:
    """Validate attachment field array values on EventDetailsSerializer.to_internal_value.

    Validation is FORMAT-ONLY: any array of well-formed ``{"uploadId": "<uuid>"}``
    objects passes.  Ownership, existence, and file type are not checked.
    """

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _serializer(self, event_type):
        req = _make_request(self.user)
        event = _make_event(event_type, self.user)
        return EventDetailsSerializer(instance=event, context={"request": req})

    # -- Accepted values --

    def test_null_value_accepted(self, v2_attachment_event_type) -> None:
        """null / None is accepted (field is optional)."""
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": None})
        assert result["photo"] is None

    def test_omitted_field_accepted(self, v2_attachment_event_type) -> None:
        """Absent field is accepted."""
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {})
        assert "photo" not in result

    def test_empty_list_accepted(self, v2_attachment_event_type) -> None:
        """An empty list is accepted when no minItems bound is set."""
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": []})
        assert result["photo"] == []

    def test_single_upload_object_accepted(self, v2_attachment_event_type) -> None:
        """A single-element array containing a valid upload object is accepted."""
        item = _upload_obj()
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": [item]})
        assert result["photo"] == [item]

    def test_multi_upload_object_array_accepted(self, v2_attachment_event_type) -> None:
        """A multi-element array of distinct valid upload objects is accepted."""
        items = [_upload_obj(), _upload_obj()]
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": items})
        assert result["photo"] == items

    def test_unknown_uuid_accepted_format_only(self, v2_attachment_event_type) -> None:
        """A well-formed UUID with no DB record passes (format-only)."""
        item = _upload_obj()
        ser = self._serializer(v2_attachment_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": [item]})
        assert result["photo"] == [item]

    # -- Rejected values (legacy shapes and bad formats) --

    def test_bare_uuid_string_rejected(self, v2_attachment_event_type) -> None:
        """A bare UUID string (legacy single-string shape) is rejected."""
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": str(uuid.uuid4())})
        assert "photo" in exc_info.value.detail

    def test_empty_string_rejected(self, v2_attachment_event_type) -> None:
        """An empty string is rejected."""
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": ""})
        assert "photo" in exc_info.value.detail

    def test_plain_uuid_string_item_rejected(self, v2_attachment_event_type) -> None:
        """An array containing a plain UUID string (not wrapped in an object) is rejected."""
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [str(uuid.uuid4())]})
        assert "photo" in exc_info.value.detail

    def test_item_missing_upload_id_rejected(self, v2_attachment_event_type) -> None:
        """An array item dict without the 'uploadId' key is rejected."""
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [{}]})
        assert "photo" in exc_info.value.detail

    def test_item_with_extra_key_rejected(self, v2_attachment_event_type) -> None:
        """An array item dict with an extra key besides 'uploadId' is rejected."""
        uid = str(uuid.uuid4())
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [{"uploadId": uid, "extra": "bad"}]})
        assert "photo" in exc_info.value.detail

    def test_upload_id_malformed_rejected(self, v2_attachment_event_type) -> None:
        """An item with a malformed uploadId value is rejected."""
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [{"uploadId": "not-a-uuid"}]})
        assert "photo" in exc_info.value.detail

    def test_duplicate_upload_ids_rejected(self, v2_attachment_event_type) -> None:
        """An array with duplicate uploadId values is rejected."""
        uid = str(uuid.uuid4())
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [{"uploadId": uid}, {"uploadId": uid}]})
        assert "photo" in exc_info.value.detail

    def test_integer_value_rejected(self, v2_attachment_event_type) -> None:
        """An integer (not a list) is rejected."""
        ser = self._serializer(v2_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": 99})
        assert "photo" in exc_info.value.detail

    # -- minItems enforcement --

    def test_empty_list_rejected_when_min_items_2(self, v2_attachment_min2_event_type) -> None:
        """An empty list fails when schema specifies minItems: 2."""
        ser = self._serializer(v2_attachment_min2_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": []})
        assert "photo" in exc_info.value.detail

    def test_non_empty_list_below_min_items_rejected(self, v2_attachment_min2_event_type) -> None:
        """A non-empty list shorter than minItems is rejected (not just the empty-list case)."""
        ser = self._serializer(v2_attachment_min2_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [_upload_obj()]})
        assert "photo" in exc_info.value.detail

    def test_list_satisfying_min_items_accepted(self, v2_attachment_min2_event_type) -> None:
        """A list with exactly minItems=2 elements is accepted."""
        items = [_upload_obj(), _upload_obj()]
        ser = self._serializer(v2_attachment_min2_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": items})
        assert result["photo"] == items

    def test_null_accepted_regardless_of_min_items(self, v2_attachment_min2_event_type) -> None:
        """None is accepted even when minItems >= 1 (absence != empty)."""
        ser = self._serializer(v2_attachment_min2_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": None})
        assert result["photo"] is None

    # -- maxItems enforcement --

    def test_max_items_0_with_nonempty_array_rejected(self, v2_attachment_max0_event_type) -> None:
        """A non-empty array fails when maxItems: 0."""
        ser = self._serializer(v2_attachment_max0_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": [_upload_obj()]})
        assert "photo" in exc_info.value.detail

    def test_max_items_0_empty_array_accepted(self, v2_attachment_max0_event_type) -> None:
        """An empty array is accepted even when maxItems: 0."""
        ser = self._serializer(v2_attachment_max0_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": []})
        assert result["photo"] == []

    def test_array_exceeding_max_items_rejected(self, v2_attachment_max1_event_type) -> None:
        """A list with more items than maxItems is rejected."""
        items = [_upload_obj(), _upload_obj()]
        ser = self._serializer(v2_attachment_max1_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": items})
        assert "photo" in exc_info.value.detail

    def test_array_within_max_items_accepted(self, v2_attachment_max1_event_type) -> None:
        """A list with exactly maxItems elements is accepted."""
        item = _upload_obj()
        ser = self._serializer(v2_attachment_max1_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": [item]})
        assert result["photo"] == [item]

    # -- Collection-nested attachment validation --

    def test_collection_nested_single_upload_object_accepted(self, v2_collection_attachment_event_type) -> None:
        """A single-element upload object array in a collection-nested attachment is accepted."""
        item = _upload_obj()
        ser = self._serializer(v2_collection_attachment_event_type)
        data = {"arrests": [{"arrestee_photo": [item]}]}
        result = ser._to_internal_value_inner(ser.instance, data)
        assert result["arrests"][0]["arrestee_photo"] == [item]

    def test_collection_nested_multi_upload_object_array_accepted(self, v2_collection_attachment_event_type) -> None:
        """A multi-element upload object array in a collection-nested attachment is accepted."""
        items = [_upload_obj(), _upload_obj()]
        ser = self._serializer(v2_collection_attachment_event_type)
        data = {"arrests": [{"arrestee_photo": items}]}
        result = ser._to_internal_value_inner(ser.instance, data)
        assert result["arrests"][0]["arrestee_photo"] == items

    def test_collection_nested_bare_string_rejected(self, v2_collection_attachment_event_type) -> None:
        """A bare UUID string (not an array) in a collection-nested attachment is rejected."""
        ser = self._serializer(v2_collection_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"arrests": [{"arrestee_photo": str(uuid.uuid4())}]})
        assert "arrests.arrestee_photo" in exc_info.value.detail

    def test_collection_nested_plain_uuid_item_rejected(self, v2_collection_attachment_event_type) -> None:
        """A plain UUID string item (not wrapped in an object) in a collection-nested attachment is rejected."""
        ser = self._serializer(v2_collection_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"arrests": [{"arrestee_photo": [str(uuid.uuid4())]}]})
        assert "arrests.arrestee_photo" in exc_info.value.detail

    def test_collection_nested_item_missing_upload_id_rejected(self, v2_collection_attachment_event_type) -> None:
        """An item dict missing 'uploadId' in a collection-nested attachment is rejected."""
        ser = self._serializer(v2_collection_attachment_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"arrests": [{"arrestee_photo": [{}]}]})
        assert "arrests.arrestee_photo" in exc_info.value.detail

    def test_collection_nested_null_accepted(self, v2_collection_attachment_event_type) -> None:
        """Null in a collection-nested attachment is accepted."""
        ser = self._serializer(v2_collection_attachment_event_type)
        data = {"arrests": [{"arrestee_photo": None}]}
        result = ser._to_internal_value_inner(ser.instance, data)
        assert result["arrests"][0]["arrestee_photo"] is None

    # -- V1 event type unaffected --

    def test_v1_event_type_bypasses_validation(self, v1_event_type) -> None:
        """V1 event types do not go through attachment validation."""
        ser = self._serializer(v1_event_type)
        result = ser._to_internal_value_inner(ser.instance, {"photo": "not-a-uuid"})
        assert result["photo"] == "not-a-uuid"

    # -- PATCH / deferred re-validation path --

    def test_patch_path_applies_same_object_validation(self, v2_attachment_event_type) -> None:
        """The deferred _internal_validated re-validation (PATCH path) enforces object item rules."""
        item = _upload_obj()
        ser = self._serializer(v2_attachment_event_type)
        # Simulate instance=None path (deferred)
        deferred = ser._to_internal_value_inner(None, {"photo": [item]})
        assert deferred["_internal_validated"] is False

        # Now simulate re-validation on update with a bad value
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(ser.instance, {"photo": "bare-uuid-string"})
        assert "photo" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Metadata sidecar: _collect_attachment_uuids and persistence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestCollectAttachmentUuidsArray:
    """_collect_attachment_uuids extracts uploadId values from object-item arrays."""

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def test_single_upload_object_collected(self, v2_attachment_event_type) -> None:
        """A single upload object's uploadId is collected."""
        uid = str(uuid.uuid4())
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": [{"uploadId": uid}]})
        assert uid in result

    def test_multiple_upload_objects_all_collected(self, v2_attachment_event_type) -> None:
        """All uploadId values in a multi-element array are collected."""
        uids = {str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())}
        items = [{"uploadId": uid} for uid in uids]
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": items})
        assert result == uids

    def test_none_value_yields_no_uuids(self, v2_attachment_event_type) -> None:
        """None field value yields no UUIDs."""
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": None})
        assert result == set()

    def test_empty_list_yields_no_uuids(self, v2_attachment_event_type) -> None:
        """Empty list yields no UUIDs."""
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": []})
        assert result == set()

    def test_absent_field_yields_no_uuids(self, v2_attachment_event_type) -> None:
        """Absent field yields no UUIDs."""
        result = _collect_attachment_uuids(v2_attachment_event_type, {})
        assert result == set()

    def test_bare_uuid_string_yields_no_uuids(self, v2_attachment_event_type) -> None:
        """A bare UUID string (non-list) is silently skipped during collection."""
        uid = str(uuid.uuid4())
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": uid})
        assert result == set()

    def test_plain_string_item_skipped(self, v2_attachment_event_type) -> None:
        """A plain string item (not a dict) in the array is silently skipped during collection."""
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": [str(uuid.uuid4())]})
        assert result == set()

    def test_item_missing_upload_id_skipped(self, v2_attachment_event_type) -> None:
        """An item dict missing 'uploadId' is silently skipped during collection."""
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": [{"other": "value"}]})
        assert result == set()

    def test_item_with_malformed_upload_id_skipped(self, v2_attachment_event_type) -> None:
        """An item dict with a malformed uploadId is silently skipped during collection."""
        result = _collect_attachment_uuids(v2_attachment_event_type, {"photo": [{"uploadId": "not-uuid"}]})
        assert result == set()

    def test_v1_event_type_yields_empty(self, v1_event_type) -> None:
        """V1 event types always yield an empty set."""
        uid = str(uuid.uuid4())
        result = _collect_attachment_uuids(v1_event_type, {"photo": [{"uploadId": uid}]})
        assert result == set()

    def test_collection_nested_upload_ids_collected(self, v2_collection_attachment_event_type) -> None:
        """uploadId values inside collection-nested attachment arrays are collected."""
        uid1, uid2 = str(uuid.uuid4()), str(uuid.uuid4())
        data = {
            "arrests": [
                {"arrestee_photo": [{"uploadId": uid1}]},
                {"arrestee_photo": [{"uploadId": uid2}]},
            ]
        }
        result = _collect_attachment_uuids(v2_collection_attachment_event_type, data)
        assert result == {uid1, uid2}


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAttachmentSidecarPersistenceArray:
    """Sidecar metadata.attachments holds all uploadId UUIDs from multi-item attachment fields."""

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    def _context(self):
        req = _make_request(self.user)
        req.build_absolute_uri = lambda path: f"http://testserver{path}"
        return {"request": req}

    def _create_event(self, event_type_value, event_details):
        from activity.serializers import EventSerializer

        data = {"event_type": event_type_value, "title": "Test", "event_details": event_details}
        ser = EventSerializer(data=data, context=self._context())
        assert ser.is_valid(), ser.errors
        return ser.save()

    def test_multi_upload_object_array_stores_all_placeholders(self, v2_attachment_event_type) -> None:
        """Creating an event with a multi-item upload object array stores a placeholder for each uploadId."""
        uid1, uid2 = str(uuid.uuid4()), str(uuid.uuid4())
        items = [{"uploadId": uid1}, {"uploadId": uid2}]
        event = self._create_event(v2_attachment_event_type.value, {"photo": items})
        details = EventDetails.objects.filter(event=event).order_by("created_at").last()
        assert details is not None
        attachments = details.data["metadata"]["attachments"]
        assert uid1 in attachments
        assert uid2 in attachments
        assert attachments[uid1] == {}
        assert attachments[uid2] == {}

    def test_single_upload_object_stores_placeholder(self, v2_attachment_event_type) -> None:
        """Creating an event with a single upload object stores exactly one placeholder."""
        uid = str(uuid.uuid4())
        event = self._create_event(v2_attachment_event_type.value, {"photo": [{"uploadId": uid}]})
        details = EventDetails.objects.filter(event=event).order_by("created_at").last()
        assert details is not None
        assert details.data["metadata"]["attachments"] == {uid: {}}

    def test_empty_array_stores_no_metadata(self, v2_attachment_event_type) -> None:
        """An empty array produces no metadata sidecar entry."""
        event = self._create_event(v2_attachment_event_type.value, {"photo": []})
        details = EventDetails.objects.filter(event=event).order_by("created_at").last()
        assert details is not None
        assert "metadata" not in details.data

    def test_update_replaces_all_placeholders(self, v2_attachment_event_type) -> None:
        """Updating to a new upload object array replaces all previous placeholders."""
        from activity.serializers import EventSerializer

        uid_old = str(uuid.uuid4())
        event = self._create_event(v2_attachment_event_type.value, {"photo": [{"uploadId": uid_old}]})

        uid_new1, uid_new2 = str(uuid.uuid4()), str(uuid.uuid4())
        update_ser = EventSerializer(
            instance=event,
            data={"event_details": {"photo": [{"uploadId": uid_new1}, {"uploadId": uid_new2}]}},
            context=self._context(),
        )
        assert update_ser.is_valid(), update_ser.errors
        update_ser.save()

        details = EventDetails.objects.filter(event=event).order_by("created_at").last()
        assert details is not None
        attachments = details.data["metadata"]["attachments"]
        assert uid_old not in attachments
        assert uid_new1 in attachments
        assert uid_new2 in attachments


# ---------------------------------------------------------------------------
# Regression: dotted ui.fields key for collection-nested attachment slots
# ---------------------------------------------------------------------------


class TestDottedKeyCollectionNestedAttachmentSlots:
    """Regression tests for ERA-13420 dotted-key convention.

    Before this fix, the ui.fields key for a collection-nested ATTACHMENT
    was the simple leaf name (e.g. ``"arrestee_photo"``), which caused:
    - ``get_field_schema_from_prop_path`` to mis-resolve bounds (looking up
      ``["arrestee_photo"]`` instead of ``["arrests", "arrestee_photo"]``).
    - ``container.get("arrestee_photo")`` to silently return ``None`` when
      iterating collection items (because items are keyed by the simple leaf,
      but the dot-prefixed slot key was used for lookup).

    With the dotted-key convention, the ui.fields key is the dotted id
    (``"arrests.arrestee_photo"``), ``data_key`` returns the simple leaf
    ``"arrestee_photo"``, and the prop-path is built by splitting on ``.``.
    """

    def _result(self, schema: dict[str, Any]) -> SchemaResult:
        return SchemaResult(event_type_value="test", schema=schema)

    def test_dotted_key_slot_has_correct_collection_parent_and_data_key(self) -> None:
        """extract_attachment_slots returns a slot keyed by the dotted id with correct routing."""
        schema = _collection_attachment_schema("arrests", "arrestee_photo", min_items=1, max_items=3)
        slots = self._result(schema).extract_attachment_slots()

        # Slot must be stored under the dotted key
        assert "arrests.arrestee_photo" in slots
        slot = slots["arrests.arrestee_photo"]

        # collection_parent and data_key derived from the dotted id
        assert slot.collection_parent == "arrests"
        assert slot.data_key == "arrestee_photo"

    def test_dotted_key_slot_resolves_bounds_from_nested_json_definition(self) -> None:
        """Dotted-path traversal resolves minItems/maxItems from inside the collection's items.properties.

        This is the primary regression: before the fix, bounds were always None
        for collection-nested fields because the prop-path was wrong.
        """
        schema = _collection_attachment_schema("arrests", "arrestee_photo", min_items=2, max_items=4)
        slots = self._result(schema).extract_attachment_slots()
        slot = slots["arrests.arrestee_photo"]

        assert slot.field.min_items == 2, "minItems must be extracted via dotted prop-path traversal"
        assert slot.field.max_items == 4, "maxItems must be extracted via dotted prop-path traversal"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDottedKeyCollectionNestedFullPipeline:
    """End-to-end regression for dotted-key collection-nested attachment pipeline.

    Verifies that validation, normalization, and UUID collection all use
    ``data_key`` (the simple leaf) rather than the dotted slot key, so that
    they correctly read from collection-item dicts like
    ``{"arrestee_photo": [...]}`` rather than looking up ``"arrests.arrestee_photo"``.
    """

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    @pytest.fixture
    def event_category(self):
        return EventCategoryFactory.create(value="dotted_key_reg_cat")

    @pytest.fixture
    def v2_collection_bounded_event_type(self, event_category):
        """V2 event type with a collection-nested attachment with minItems=1 and maxItems=2."""
        return EventTypeFactory.create(
            category=event_category,
            value="v2_dotted_key_reg",
            schema=json.dumps(_collection_attachment_schema("arrests", "arrestee_photo", min_items=1, max_items=2)),
            version=EventType.VersionChoices.VERSION_2,
        )

    def _serializer(self, event_type):
        req = _make_request(self.user)
        event = Event.objects.create(
            title="Dotted-key regression",
            event_type=event_type,
            created_by_user=self.user,
            state="new",
        )
        return EventDetailsSerializer(instance=event, context={"request": req})

    def test_bounds_enforced_for_collection_nested_attachment_via_dotted_key(
        self, v2_collection_bounded_event_type
    ) -> None:
        """minItems bound on a collection-nested attachment is enforced when data uses the simple leaf key.

        Before the fix: bounds were always None (prop-path mis-traversal), so
        an empty array passed silently.  After the fix: minItems=1 is enforced.
        """
        ser = self._serializer(v2_collection_bounded_event_type)
        # Empty array for the nested attachment — should fail minItems=1
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(
                ser.instance,
                {"arrests": [{"arrestee_photo": []}]},
            )
        # Error keyed by the dotted field id
        assert "arrests.arrestee_photo" in exc_info.value.detail

    def test_normalization_applied_to_collection_nested_attachment_via_dotted_key(
        self, v2_collection_bounded_event_type
    ) -> None:
        """Normalization rewrites uploadId to canonical form for collection-nested attachments.

        Before the fix: ``container.get("arrests.arrestee_photo")`` returned None
        (data keyed by simple leaf), so normalization was silently skipped.
        """
        uid = str(uuid.uuid4())
        uppercase_uid = uid.upper()
        ser = self._serializer(v2_collection_bounded_event_type)
        result = ser._to_internal_value_inner(
            ser.instance,
            {"arrests": [{"arrestee_photo": [{"uploadId": uppercase_uid}]}]},
        )
        # uploadId must be normalised to canonical lowercase form
        stored = result["arrests"][0]["arrestee_photo"][0]["uploadId"]
        assert stored == uid

    def test_collect_attachment_uuids_returns_nested_uuid_via_dotted_key(
        self, v2_collection_bounded_event_type
    ) -> None:
        """_collect_attachment_uuids extracts UUIDs from collection-nested attachments via data_key.

        Before the fix: ``container.get("arrests.arrestee_photo")`` returned None,
        so UUIDs were never collected for nested slots.
        """
        uid = str(uuid.uuid4())
        data = {"arrests": [{"arrestee_photo": [{"uploadId": uid}]}]}
        result = _collect_attachment_uuids(v2_collection_bounded_event_type, data)
        assert uid in result, "UUID from collection-nested attachment must be collected via data_key lookup"


# ---------------------------------------------------------------------------
# Double-nested collection (outer.inner.photo) — arbitrary depth support
# ---------------------------------------------------------------------------


def _double_nested_collection_attachment_schema(
    outer: str = "outer",
    inner: str = "inner",
    attachment_field: str = "photo",
    allowable_file_types: list[str] | None = None,
    min_items: int | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    """Build a V2 schema with an ATTACHMENT inside a COLLECTION inside a COLLECTION.

    JSON shape::

        {
          "outer": [
            {
              "inner": [
                {"photo": [{"uploadId": "<uuid>"}]}
              ]
            }
          ]
        }

    UI shape::

        ui.fields = {
            "outer":            COLLECTION, parent "section-1"
            "outer.inner":      COLLECTION, parent "outer"
            "outer.inner.photo": ATTACHMENT, parent "outer.inner"
        }
    """
    if allowable_file_types is None:
        allowable_file_types = []
    dotted_inner = f"{outer}.{inner}"
    dotted_attachment = f"{outer}.{inner}.{attachment_field}"
    return {
        "json": {
            "$schema": _V2_DRAFT,
            "type": "object",
            "properties": {
                outer: {
                    "deprecated": False,
                    "items": {
                        "type": "object",
                        "properties": {
                            inner: {
                                "deprecated": False,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        attachment_field: _attachment_field_json_def(
                                            min_items=min_items, max_items=max_items
                                        ),
                                    },
                                    "required": [],
                                    "unevaluatedProperties": False,
                                },
                                "title": inner.replace("_", " ").title(),
                                "type": "array",
                                "unevaluatedItems": False,
                            }
                        },
                        "required": [],
                        "unevaluatedProperties": False,
                    },
                    "title": outer.replace("_", " ").title(),
                    "type": "array",
                    "unevaluatedItems": False,
                }
            },
            "required": [],
            "unevaluatedProperties": False,
        },
        "ui": {
            "fields": {
                outer: {
                    "buttonText": "Add",
                    "columns": 1,
                    "itemIdentifier": "",
                    "itemName": "Outer Item",
                    "leftColumn": [dotted_inner],
                    "rightColumn": [],
                    "type": "COLLECTION",
                    "parent": "section-1",
                },
                dotted_inner: {
                    "buttonText": "Add",
                    "columns": 1,
                    "itemIdentifier": "",
                    "itemName": "Inner Item",
                    "leftColumn": [dotted_attachment],
                    "rightColumn": [],
                    "type": "COLLECTION",
                    "parent": outer,
                },
                dotted_attachment: {
                    "allowableFileTypes": allowable_file_types,
                    "type": "ATTACHMENT",
                    "parent": dotted_inner,
                },
            },
            "headers": {},
            "order": ["section-1"],
            "sections": {
                "section-1": {
                    "columns": 1,
                    "isActive": True,
                    "label": "",
                    "leftColumn": [{"name": outer, "type": "field"}],
                    "rightColumn": [],
                }
            },
        },
    }


class TestDottedKeyDoubleNestedAttachmentSlots:
    """Unit tests for ATTACHMENT two COLLECTION levels deep (outer.inner.photo).

    Verifies that ``extract_attachment_slots`` and ``Slot`` properties return
    correct values for a field_id with two dots, and that ``value_containers``
    descends through both collection levels.
    """

    def _result(self, schema: dict[str, Any]) -> SchemaResult:
        return SchemaResult(event_type_value="test", schema=schema)

    def test_extract_slots_returns_slot_keyed_by_doubly_dotted_id(self) -> None:
        """extract_attachment_slots returns a slot keyed by the full doubly-dotted id."""
        schema = _double_nested_collection_attachment_schema("outer", "inner", "photo")
        slots = self._result(schema).extract_attachment_slots()
        assert "outer.inner.photo" in slots

    def test_slot_data_key_is_leaf_segment(self) -> None:
        """data_key is the simple leaf name (last segment of the dotted id)."""
        schema = _double_nested_collection_attachment_schema("outer", "inner", "photo")
        slot = self._result(schema).extract_attachment_slots()["outer.inner.photo"]
        assert slot.data_key == "photo"

    def test_slot_collection_parent_is_immediate_enclosing_collection(self) -> None:
        """collection_parent is the immediate (innermost) enclosing collection — not the compound string."""
        schema = _double_nested_collection_attachment_schema("outer", "inner", "photo")
        slot = self._result(schema).extract_attachment_slots()["outer.inner.photo"]
        assert slot.collection_parent == "inner"

    def test_slot_collection_path_contains_both_collection_names(self) -> None:
        """collection_path lists both collection names in outermost-first order."""
        schema = _double_nested_collection_attachment_schema("outer", "inner", "photo")
        slot = self._result(schema).extract_attachment_slots()["outer.inner.photo"]
        assert slot.collection_path == ["outer", "inner"]

    def test_slot_min_items_extracted_via_double_nesting(self) -> None:
        """minItems is extracted correctly from a doubly-nested attachment field."""
        schema = _double_nested_collection_attachment_schema("outer", "inner", "photo", min_items=2)
        slot = self._result(schema).extract_attachment_slots()["outer.inner.photo"]
        assert slot.field.min_items == 2

    def test_slot_max_items_extracted_via_double_nesting(self) -> None:
        """maxItems is extracted correctly from a doubly-nested attachment field."""
        schema = _double_nested_collection_attachment_schema("outer", "inner", "photo", max_items=3)
        slot = self._result(schema).extract_attachment_slots()["outer.inner.photo"]
        assert slot.field.max_items == 3


class TestDoubleNestedValueContainers:
    """Unit tests for Slot.value_containers with a doubly-nested field_id.

    Uses a minimal Slot (with a stub AttachmentField) to isolate the descent
    logic without going through the full pipeline.
    """

    def _slot(self, field_id: str) -> "Slot[Any]":
        from activity.schemas.eventtype_service import AttachmentField, Slot

        return Slot(
            field=AttachmentField(allowable_file_types=[]),
            field_id=field_id,
        )

    def test_single_outer_single_inner_yields_innermost_dict(self) -> None:
        """value_containers for 'outer.inner.photo' yields the single innermost item-dict."""
        slot = self._slot("outer.inner.photo")
        inner_item = {"photo": [_upload_obj()]}
        data = {"outer": [{"inner": [inner_item]}]}
        result = list(slot.value_containers(data))
        assert result == [inner_item]

    def test_multiple_outer_items_each_expanded(self) -> None:
        """value_containers yields innermost dicts from every outer item's inner list."""
        slot = self._slot("outer.inner.photo")
        inner_a = {"photo": [_upload_obj()]}
        inner_b = {"photo": [_upload_obj()]}
        data = {
            "outer": [
                {"inner": [inner_a]},
                {"inner": [inner_b]},
            ]
        }
        result = list(slot.value_containers(data))
        assert result == [inner_a, inner_b]

    def test_multiple_inner_items_within_one_outer_all_yielded(self) -> None:
        """value_containers yields all inner-level dicts when a single outer item has multiple inner items."""
        slot = self._slot("outer.inner.photo")
        inner_x = {"photo": [_upload_obj()]}
        inner_y = {"photo": [_upload_obj()]}
        data = {"outer": [{"inner": [inner_x, inner_y]}]}
        result = list(slot.value_containers(data))
        assert result == [inner_x, inner_y]

    def test_cartesian_expansion_multiple_outer_and_multiple_inner(self) -> None:
        """value_containers yields all M×N innermost dicts (2 outer × 2 inner = 4 results)."""
        slot = self._slot("outer.inner.photo")
        items = [[{"photo": [_upload_obj()]}, {"photo": [_upload_obj()]}] for _ in range(2)]
        data = {
            "outer": [
                {"inner": items[0]},
                {"inner": items[1]},
            ]
        }
        expected = items[0] + items[1]
        result = list(slot.value_containers(data))
        assert result == expected

    def test_missing_outer_yields_nothing(self) -> None:
        """If the outer collection key is absent, value_containers yields nothing."""
        slot = self._slot("outer.inner.photo")
        result = list(slot.value_containers({"unrelated": [{"inner": [{"photo": []}]}]}))
        assert result == []

    def test_outer_non_list_yields_nothing(self) -> None:
        """If the outer collection value is not a list, value_containers yields nothing."""
        slot = self._slot("outer.inner.photo")
        result = list(slot.value_containers({"outer": "not-a-list"}))
        assert result == []

    def test_missing_inner_skipped_gracefully(self) -> None:
        """An outer item with no 'inner' key is skipped; others are still descended."""
        slot = self._slot("outer.inner.photo")
        inner_item = {"photo": [_upload_obj()]}
        data = {
            "outer": [
                {},  # no "inner" key
                {"inner": [inner_item]},
            ]
        }
        result = list(slot.value_containers(data))
        assert result == [inner_item]

    def test_non_dict_inner_items_skipped(self) -> None:
        """Non-dict items in the inner list are silently skipped."""
        slot = self._slot("outer.inner.photo")
        inner_item = {"photo": [_upload_obj()]}
        data = {"outer": [{"inner": ["not-a-dict", None, inner_item]}]}
        result = list(slot.value_containers(data))
        assert result == [inner_item]

    def test_flat_slot_still_yields_data_directly(self) -> None:
        """A flat slot (no dots) still yields data itself — regression guard."""
        slot = self._slot("photo")
        data = {"photo": [_upload_obj()]}
        result = list(slot.value_containers(data))
        assert result == [data]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDottedKeyDoubleNestedFullPipeline:
    """End-to-end tests for the doubly-nested attachment pipeline (outer.inner.photo).

    Covers validation, bounds enforcement, normalization, and UUID collection for
    a field_id with two dots (two enclosing COLLECTIONs).
    """

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user):
        self.user = admin_user

    @pytest.fixture
    def event_category(self):
        return EventCategoryFactory.create(value="double_nested_cat")

    @pytest.fixture
    def v2_double_nested_event_type(self, event_category):
        """V2 event type with outer → inner → photo (no bounds)."""
        return EventTypeFactory.create(
            category=event_category,
            value="v2_double_nested",
            schema=json.dumps(_double_nested_collection_attachment_schema("outer", "inner", "photo", ["image"])),
            version=EventType.VersionChoices.VERSION_2,
        )

    @pytest.fixture
    def v2_double_nested_bounded_event_type(self, event_category):
        """V2 event type with outer → inner → photo, minItems=1, maxItems=2."""
        return EventTypeFactory.create(
            category=event_category,
            value="v2_double_nested_bounded",
            schema=json.dumps(
                _double_nested_collection_attachment_schema("outer", "inner", "photo", min_items=1, max_items=2)
            ),
            version=EventType.VersionChoices.VERSION_2,
        )

    def _serializer(self, event_type):
        req = _make_request(self.user)
        event = _make_event(event_type, self.user)
        return EventDetailsSerializer(instance=event, context={"request": req})

    def test_valid_doubly_nested_upload_object_accepted(self, v2_double_nested_event_type) -> None:
        """A well-formed upload object two collections deep passes validation."""
        item = _upload_obj()
        ser = self._serializer(v2_double_nested_event_type)
        data = {"outer": [{"inner": [{"photo": [item]}]}]}
        result = ser._to_internal_value_inner(ser.instance, data)
        assert result["outer"][0]["inner"][0]["photo"] == [item]

    def test_bounds_enforced_for_doubly_nested_attachment(self, v2_double_nested_bounded_event_type) -> None:
        """minItems=1 bound on a doubly-nested attachment is enforced (empty array rejected)."""
        ser = self._serializer(v2_double_nested_bounded_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(
                ser.instance,
                {"outer": [{"inner": [{"photo": []}]}]},
            )
        assert "outer.inner.photo" in exc_info.value.detail

    def test_max_items_bound_enforced_for_doubly_nested_attachment(self, v2_double_nested_bounded_event_type) -> None:
        """maxItems=2 bound on a doubly-nested attachment is enforced (3 items rejected)."""
        ser = self._serializer(v2_double_nested_bounded_event_type)
        items = [_upload_obj(), _upload_obj(), _upload_obj()]
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(
                ser.instance,
                {"outer": [{"inner": [{"photo": items}]}]},
            )
        assert "outer.inner.photo" in exc_info.value.detail

    def test_duplicate_upload_ids_rejected_in_doubly_nested_attachment(self, v2_double_nested_event_type) -> None:
        """Duplicate uploadId values in a doubly-nested attachment are rejected."""
        uid = str(uuid.uuid4())
        ser = self._serializer(v2_double_nested_event_type)
        with pytest.raises(ValidationError) as exc_info:
            ser._to_internal_value_inner(
                ser.instance,
                {"outer": [{"inner": [{"photo": [{"uploadId": uid}, {"uploadId": uid}]}]}]},
            )
        assert "outer.inner.photo" in exc_info.value.detail

    def test_normalization_applied_to_doubly_nested_attachment(self, v2_double_nested_event_type) -> None:
        """Normalization rewrites uploadId to canonical form for doubly-nested attachments."""
        uid = str(uuid.uuid4())
        uppercase_uid = uid.upper()
        ser = self._serializer(v2_double_nested_event_type)
        result = ser._to_internal_value_inner(
            ser.instance,
            {"outer": [{"inner": [{"photo": [{"uploadId": uppercase_uid}]}]}]},
        )
        stored = result["outer"][0]["inner"][0]["photo"][0]["uploadId"]
        assert stored == uid, "uploadId must be normalised to canonical lowercase form"

    def test_urn_upload_id_normalized_in_doubly_nested_attachment(self, v2_double_nested_event_type) -> None:
        """A urn:uuid: uploadId in a doubly-nested attachment is normalized to canonical form."""
        uid = str(uuid.uuid4())
        urn_form = f"urn:uuid:{uid}"
        ser = self._serializer(v2_double_nested_event_type)
        result = ser._to_internal_value_inner(
            ser.instance,
            {"outer": [{"inner": [{"photo": [{"uploadId": urn_form}]}]}]},
        )
        stored = result["outer"][0]["inner"][0]["photo"][0]["uploadId"]
        assert stored == uid

    def test_collect_attachment_uuids_returns_doubly_nested_uuid(self, v2_double_nested_event_type) -> None:
        """_collect_attachment_uuids extracts UUIDs from doubly-nested attachment fields."""
        uid = str(uuid.uuid4())
        data = {"outer": [{"inner": [{"photo": [{"uploadId": uid}]}]}]}
        result = _collect_attachment_uuids(v2_double_nested_event_type, data)
        assert uid in result, "UUID from doubly-nested attachment must be collected"

    def test_collect_attachment_uuids_from_multiple_outer_and_inner_items(self, v2_double_nested_event_type) -> None:
        """_collect_attachment_uuids collects UUIDs across all outer and inner items."""
        uid1, uid2, uid3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        data = {
            "outer": [
                {"inner": [{"photo": [{"uploadId": uid1}]}, {"photo": [{"uploadId": uid2}]}]},
                {"inner": [{"photo": [{"uploadId": uid3}]}]},
            ]
        }
        result = _collect_attachment_uuids(v2_double_nested_event_type, data)
        assert result == {uid1, uid2, uid3}

    def test_null_photo_in_doubly_nested_attachment_accepted(self, v2_double_nested_event_type) -> None:
        """Null is accepted for a doubly-nested attachment field."""
        ser = self._serializer(v2_double_nested_event_type)
        data = {"outer": [{"inner": [{"photo": None}]}]}
        result = ser._to_internal_value_inner(ser.instance, data)
        assert result["outer"][0]["inner"][0]["photo"] is None
