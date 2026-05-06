import json

import pytest

from activity.factories import EventFactory, EventSourceEventFactory, EventSourceFactory
from activity.models import EventType
from activity.tests.helpers.schema_test_utils import V2SchemaBuilder
from factories import EventTypeFactory


@pytest.fixture
def base_event():
    return EventFactory.create()


@pytest.fixture
def event_source_event():
    return EventSourceEventFactory.create()


@pytest.fixture
def event_with_event_source_event(base_event):
    EventSourceEventFactory.create(event=base_event)
    return base_event


@pytest.fixture
def event_source():
    return EventSourceFactory.create()


@pytest.fixture
def collection_event_type(five_event_categories):
    security_category = [
        event_category for event_category in five_event_categories if event_category.value == "security"
    ][0]

    schema = V2SchemaBuilder.multi_field(
        {
            "conservancy": {"existing_choices": ["conservancy"], "title": "Conservancy (Incident Field)"},
            "station": {"existing_choices": ["station"], "title": "Reporting Station (Incident Field)"},
            "reportingtime": {"format": "date-time", "title": "Reporting Time (Incident Field)"},
        }
    )
    return EventTypeFactory.create(
        category=security_category,
        is_collection=True,
        schema=json.dumps(schema),
        value="incident_collection",
        display="Incident Collection",
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def logistics_event_type(five_event_categories):
    security_category = [
        event_category for event_category in five_event_categories if event_category.value == "security"
    ][0]
    return EventTypeFactory.create(
        category=security_category,
        value="logistics",
        display="Logistics",
    )


@pytest.fixture
def monitoring_event_type(five_event_categories):
    monitoring_category = [
        event_category for event_category in five_event_categories if event_category.value == "monitoring"
    ][0]
    return EventTypeFactory.create(
        category=monitoring_category,
        value="monitoring",
        display="Monitoring",
    )


@pytest.fixture
def base_event_types(collection_event_type, logistics_event_type, monitoring_event_type):
    """Fixture for base event types."""
    return collection_event_type, logistics_event_type, monitoring_event_type


@pytest.fixture
def cat1_fire_v2_event_type(cat1_cat2_categories):
    cat1, _ = cat1_cat2_categories

    schema = {
        "json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "unevaluatedProperties": False,
            "properties": {
                "comments": {
                    "default": "",
                    "deprecated": False,
                    "description": "Extra information.",
                    "title": "Comments",
                    "type": "string",
                },
                "status": {
                    "deprecated": False,
                    "description": "",
                    "title": "Status",
                    "type": "string",
                    "anyOf": [{"$ref": "/api/v2.0/schemas/choices.json?field=firerep_status"}],
                },
                "direction": {
                    "deprecated": False,
                    "description": "Where is the fire moving to?",
                    "title": "Direction",
                    "type": "string",
                    "anyOf": [{"$ref": "/api/v2.0/schemas/choices.json?field=firerep_direction"}],
                },
                "cause": {
                    "deprecated": False,
                    "description": "",
                    "title": "Cause",
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "anyOf": [{"$ref": "/api/v2.0/schemas/choices.json?field=firerep_cause"}],
                    },
                },
                "time_fire_went_off": {
                    "deprecated": False,
                    "description": "",
                    "format": "date-time",
                    "title": "Time fire went off",
                    "type": "string",
                },
                "spot_fires": {
                    "deprecated": False,
                    "items": {
                        "unevaluatedProperties": False,
                        "properties": {
                            "spot_fire_location": {
                                "deprecated": False,
                                "description": "",
                                "properties": {
                                    "latitude": {"maximum": 90, "minimum": -90, "type": "number"},
                                    "longitude": {"maximum": 180, "minimum": -180, "type": "number"},
                                },
                                "required": ["latitude", "longitude"],
                                "unevaluatedProperties": False,
                                "title": "Location",
                                "type": "object",
                            },
                            "spot_fire_details": {
                                "default": "",
                                "deprecated": False,
                                "description": "",
                                "title": "Details",
                                "type": "string",
                            },
                        },
                        "required": ["spot_fire_location"],
                        "type": "object",
                    },
                    "title": "Spot Fires",
                    "type": "array",
                    "unevaluatedItems": False,
                },
            },
            "required": ["status"],
            "type": "object",
        },
        "ui": {
            "fields": {
                "comments": {"inputType": "LONG_TEXT", "placeholder": "", "type": "TEXT", "parent": "section-3"},
                "status": {
                    "choices": {
                        "eventTypeCategories": [],
                        "existingChoiceList": ["firerep_status"],
                        "featureCategories": [],
                        "myDataType": "",
                        "subjectGroups": [],
                        "subjectSubtypes": [],
                        "type": "EXISTING_CHOICE_LIST",
                    },
                    "inputType": "LIST",
                    "placeholder": "",
                    "type": "CHOICE_LIST",
                    "parent": "section-1",
                },
                "direction": {
                    "choices": {
                        "eventTypeCategories": [],
                        "existingChoiceList": ["firerep_direction"],
                        "featureCategories": [],
                        "myDataType": "",
                        "subjectGroups": [],
                        "subjectSubtypes": [],
                        "type": "EXISTING_CHOICE_LIST",
                    },
                    "inputType": "DROPDOWN",
                    "placeholder": "",
                    "type": "CHOICE_LIST",
                    "parent": "section-1",
                },
                "cause": {
                    "choices": {
                        "eventTypeCategories": [],
                        "existingChoiceList": ["firerep_cause"],
                        "featureCategories": [],
                        "myDataType": "",
                        "subjectGroups": [],
                        "subjectSubtypes": [],
                        "type": "EXISTING_CHOICE_LIST",
                    },
                    "inputType": "DROPDOWN",
                    "placeholder": "",
                    "type": "CHOICE_LIST",
                    "parent": "section-1",
                },
                "time_fire_went_off": {"type": "DATE_TIME", "parent": "section-2"},
                "spot_fire_location": {"type": "LOCATION", "parent": "spot_fires"},
                "spot_fire_details": {
                    "inputType": "LONG_TEXT",
                    "placeholder": "Time noticed, intensity, etc...",
                    "type": "TEXT",
                    "parent": "spot_fires",
                },
                "spot_fires": {
                    "buttonText": "Add Spot Fire",
                    "columns": 1,
                    "itemIdentifier": "spot_fire_location",
                    "itemName": "Spot Fire",
                    "leftColumn": ["spot_fire_location", "spot_fire_details"],
                    "rightColumn": [],
                    "type": "COLLECTION",
                    "parent": "section-2",
                },
            },
            "headers": {},
            "order": ["section-1", "section-2", "section-3"],
            "sections": {
                "section-2": {
                    "columns": 2,
                    "isActive": True,
                    "label": "Details",
                    "leftColumn": [{"name": "spot_fires", "type": "field"}],
                    "rightColumn": [{"name": "time_fire_went_off", "type": "field"}],
                },
                "section-3": {
                    "columns": 1,
                    "isActive": True,
                    "label": "Comments",
                    "leftColumn": [{"type": "field", "name": "comments"}],
                    "rightColumn": [],
                },
                "section-1": {
                    "columns": 2,
                    "isActive": True,
                    "label": "Fire",
                    "leftColumn": [{"name": "status", "type": "field"}, {"name": "direction", "type": "field"}],
                    "rightColumn": [{"name": "cause", "type": "field"}],
                },
            },
        },
    }

    schema = json.dumps(schema)
    v2 = EventType.VersionChoices.VERSION_2
    fire_event_type = EventTypeFactory.create(category=cat1, version=v2, schema=schema, value="fire_v2")
    return fire_event_type
