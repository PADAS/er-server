import csv
import json
from io import StringIO

import pytest

from django.urls import reverse
from rest_framework import status

from accounts.models import PermissionSet
from activity.models import EventType
from factories import (
    ChoiceFactory,
    EventCategoryFactory,
    PermissionSetFactory,
    SubjectFactory,
    SubjectGroupFactory,
)
from observations.models import SubjectSubType
from utils.csv_streaming import read_streaming_response_content

BASE_URL = "https://zoo.com/api/v2.0/schemas"


CARCASS_V2_EVENTTYPE_SCHEMA = {
    "json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "type": "object",
        "properties": {
            "carcassrep_species": {
                "deprecated": False,
                "description": "",
                "title": "Species",
                "type": "string",
                "anyOf": [{"$ref": f"{BASE_URL}/choices.json?field=carcassrep_species"}],
            },
            "carcassrep_sex": {
                "deprecated": False,
                "description": "",
                "title": "Sex of Animal",
                "type": "string",
                "anyOf": [{"$ref": f"{BASE_URL}/choices.json?field=carcassrep_sex"}],
            },
            "carcassrep_ageofanimal": {
                "deprecated": False,
                "description": "",
                "title": "Age of Animal",
                "type": "string",
                "anyOf": [{"$ref": f"{BASE_URL}/choices.json?field=carcassrep_ageofanimal"}],
            },
            "carcassrep_ageofcarcass": {
                "deprecated": False,
                "description": "",
                "title": "Age of Carcass",
                "type": "string",
                "anyOf": [{"$ref": f"{BASE_URL}/choices.json?field=carcassrep_ageofcarcass"}],
            },
            "carcassrep_trophystatus": {
                "deprecated": False,
                "description": "",
                "title": "Trophy Status",
                "type": "string",
                "anyOf": [{"$ref": f"{BASE_URL}/choices.json?field=carcassrep_trophystatus"}],
            },
            "carcassrep_causeofdeath": {
                "deprecated": False,
                "description": "",
                "title": "Cause of Death",
                "type": "string",
                "anyOf": [{"$ref": f"{BASE_URL}/choices.json?field=carcassrep_causeofdeath"}],
            },
            "carcassrep_sampledatetime": {
                "deprecated": False,
                "description": "",
                "title": "Sample Date Time",
                "type": "string",
                "format": "date-time",
            },
            "animal_groups": {
                "deprecated": False,
                "description": "",
                "items": {
                    "additionalProperties": False,
                    "properties": {
                        "species_of_group": {
                            "deprecated": False,
                            "description": "",
                            "title": "Species of Group",
                            "type": "string",
                            "anyOf": [{"$ref": f"{BASE_URL}/choices.json?field=carcassrep_species"}],
                        },
                        "number_of_animals_in_group": {
                            "deprecated": False,
                            "description": "",
                            "title": "Number of Animals in Group",
                            "type": "number",
                        },
                    },
                    "required": [],
                    "type": "object",
                },
                "title": "Animal Groups",
                "type": "array",
                "unevaluatedItems": False,
            },
            "signed_off_by": {
                "deprecated": False,
                "description": "",
                "title": "Signed Off By",
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "anyOf": [{"$ref": f"{BASE_URL}/subjects.json?subject_subtypes=ranger"}]},
            },
        },
        "required": [],
    },
    "ui": {
        "fields": {
            "carcassrep_species": {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": ["carcassrep_species"],
                    "featureCategories": [],
                    "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            },
            "carcassrep_sex": {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": ["carcassrep_sex"],
                    "featureCategories": [],
                    "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            },
            "carcassrep_ageofanimal": {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": ["carcassrep_ageofanimal"],
                    "featureCategories": [],
                    "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            },
            "carcassrep_ageofcarcass": {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": ["carcassrep_ageofcarcass"],
                    "featureCategories": [],
                    "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            },
            "carcassrep_trophystatus": {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": ["carcassrep_trophystatus"],
                    "featureCategories": [],
                    "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            },
            "carcassrep_causeofdeath": {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": ["carcassrep_causeofdeath"],
                    "featureCategories": [],
                    "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            },
            "carcassrep_sampledatetime": {
                "type": "DATE_TIME",
                "parent": "section-1",
            },
            "animal_groups": {
                "buttonText": "",
                "columns": 1,
                "itemIdentifier": "",
                "itemName": "Animal group",
                "leftColumn": ["species_of_group", "number_of_animals_in_group"],
                "rightColumn": [],
                "type": "COLLECTION",
                "parent": "section-1",
            },
            "species_of_group": {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": ["carcassrep_species"],
                    "featureCategories": [],
                    "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "animal_groups",
            },
            "number_of_animals_in_group": {"placeholder": "", "type": "NUMERIC", "parent": "animal_groups"},
            "signed_off_by": {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": [],
                    "featureCategories": [],
                    "myDataType": "SUBJECTS_FROM_SUBJECT_SUBTYPE",
                    "subjectGroups": [],
                    "subjectSubtypes": ["ranger"],
                    "type": "MY_DATA",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            },
        },
        "headers": {},
        "order": ["section-1"],
        "sections": {
            "section-1": {
                "columns": 1,
                "isActive": True,
                "label": "",
                "leftColumn": [
                    {"name": "carcassrep_species", "type": "field"},
                    {"name": "carcassrep_sex", "type": "field"},
                    {"name": "carcassrep_ageofanimal", "type": "field"},
                    {"name": "carcassrep_ageofcarcass", "type": "field"},
                    {"name": "carcassrep_trophystatus", "type": "field"},
                    {"name": "carcassrep_causeofdeath", "type": "field"},
                    {"name": "animal_groups", "type": "field"},
                    {"name": "signed_off_by", "type": "field"},
                ],
                "rightColumn": [],
            }
        },
    },
}


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestEventExport:

    @pytest.fixture(autouse=True)
    def caracass_v2_eventtype(self, superuser_client, user_client, tenant_settings, view_subject_permissions):

        ChoiceFactory.create(
            value="elephant", display="Elephant", model="activity.eventtype", field="carcassrep_species"
        )
        ChoiceFactory.create(value="eland", display="Eland", model="activity.eventtype", field="carcassrep_species")
        ChoiceFactory.create(value="rhino", display="Rhino", model="activity.eventtype", field="carcassrep_species")
        ChoiceFactory.create(value="bongo", display="Bongo", model="activity.eventtype", field="carcassrep_species")
        ChoiceFactory.create(value="buffalo", display="Buffalo", model="activity.eventtype", field="carcassrep_species")
        ChoiceFactory.create(value="sex", display="Sex of Animal", model="activity.eventtype", field="carcassrep_sex")
        ChoiceFactory.create(
            value="ageofanimal", display="Age of Animal", model="activity.eventtype", field="carcassrep_ageofanimal"
        )
        ChoiceFactory.create(
            value="ageofcarcass", display="Age of Carcass", model="activity.eventtype", field="carcassrep_ageofcarcass"
        )
        ChoiceFactory.create(
            value="trophystatus", display="Trophy Status", model="activity.eventtype", field="carcassrep_trophystatus"
        )
        ChoiceFactory.create(
            value="causeofdeath", display="Cause of Death", model="activity.eventtype", field="carcassrep_causeofdeath"
        )

        event_category = EventCategoryFactory.create(value="category 0")
        _ = event_category.auto_permissionset_name
        """Create an EventType with the given schema."""
        url = reverse("v2-eventtype-list")
        data = {
            "value": "carcass_v2_rep",
            "display": "Test EventType carcass_v2_rep",
            "category": event_category.value,
            "schema": CARCASS_V2_EVENTTYPE_SCHEMA,
            "is_active": True,
        }
        response = superuser_client.post(url, data=data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        eventtype = EventType.objects.get(value=data["value"])

        export_permission_set = PermissionSet.objects.get(name="Can Export Data")
        user_client.user.permission_sets.add(export_permission_set)
        security_permission_set = PermissionSet.objects.get(name=event_category.auto_permissionset_name)
        user_client.user.permission_sets.add(security_permission_set)

        view_subject_permission_set = PermissionSetFactory.create(permissions=view_subject_permissions)
        self.subject_group = SubjectGroupFactory.create(permission_sets=[view_subject_permission_set])
        user_client.user.permission_sets.add(view_subject_permission_set)

        self.superuser_client = superuser_client
        self.user_client = user_client
        self.event_display = data["display"]
        return eventtype

    def convert_rendered_csv_to_dict(self, content):
        reader = csv.DictReader(StringIO(content))
        return [row for row in reader]

    def test_exporting_multiple_choice_events_to_csv(self) -> None:
        multiple_choice_data = json.loads(
            """{"event_type": "carcass_v2_rep","priority":200,"event_details": {"carcassrep_species": ["elephant", "eland"]}}"""
        )

        url = reverse("events")

        response = self.user_client.post(url, multiple_choice_data)

        assert response.status_code == status.HTTP_201_CREATED

        url = reverse("events-export")

        response = self.user_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        rendered_dict = self.convert_rendered_csv_to_dict(read_streaming_response_content(response))

        assert self.event_display in [i.get("Report_Type") for i in rendered_dict]
        target_row = {}

        for row in rendered_dict:
            if row.get("Report_Type") == self.event_display:
                target_row = row
                break

        assert "Species" in target_row.keys()
        assert target_row.get("Species") == "Elephant;Eland"

    def test_exporting_multiple_choice_events_to_csv_with_qparam_value_cols_true(self):
        multiple_choice_data = json.loads(
            """{"event_type": "carcass_v2_rep","priority":200,"event_details": {"carcassrep_species": ["elephant", "eland"]}}"""
        )

        url = reverse("events")

        response = self.user_client.post(url, multiple_choice_data)

        assert response.status_code == status.HTTP_201_CREATED

        url = reverse("events-export")

        response = self.user_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        url = reverse("events-export") + "?value_cols=true"

        response = self.user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        rendered_dict = self.convert_rendered_csv_to_dict(read_streaming_response_content(response))

        assert self.event_display in [i.get("Report_Type") for i in rendered_dict]
        target_row = {}

        for row in rendered_dict:
            if row.get("Report_Type") == self.event_display:
                target_row = row
                break

        assert "Species" in target_row.keys()
        assert "carcassrep_species" in target_row.keys()
        assert target_row.get("Species") == "Elephant;Eland"
        assert target_row.get("carcassrep_species") == "elephant;eland"

    def test_exporting_collection_events_to_csv(self):
        collection_data = json.loads(
            """{"event_type": "carcass_v2_rep", "priority":200, "event_details": {"animal_groups": [{"species_of_group": "cheetah", "number_of_animals_in_group": 1}, {"species_of_group": "crocodile", "number_of_animals_in_group": 3}], "carcassrep_species": "bongo"}}"""
        )

        url = reverse("events")

        response = self.user_client.post(url, collection_data)

        assert response.status_code == status.HTTP_201_CREATED

        url = reverse("events-export")

        response = self.user_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        rendered_dict = self.convert_rendered_csv_to_dict(read_streaming_response_content(response))

        assert self.event_display in [i.get("Report_Type") for i in rendered_dict]
        target_row = {}

        for row in rendered_dict:
            if row.get("Report_Type") == self.event_display:
                target_row = row
                break
        assert "Species" in target_row.keys()
        assert target_row.get("Species") == "Bongo"
        assert "Animal_Groups" in target_row.keys()
        assert "cheetah" in target_row.get("Animal_Groups")

    def test_exporting_my_data_events_to_csv_no_uuid(self):
        ranger_subtype = SubjectSubType.objects.get(value="ranger")
        ranger = SubjectFactory.create(subject_subtype=ranger_subtype)
        ranger.groups.add(self.subject_group)
        my_data_data = {
            "event_type": "carcass_v2_rep",
            "priority": 200,
            "event_details": {
                "signed_off_by": [str(ranger.id)],
                "carcassrep_sampledatetime": "2026-02-17T01:23:00-07:00",
            },
        }

        url = reverse("events")

        response = self.user_client.post(url, my_data_data)

        assert response.status_code == status.HTTP_201_CREATED

        url = reverse("events-export")

        response = self.user_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        rendered_dict = self.convert_rendered_csv_to_dict(read_streaming_response_content(response))

        target_row = {}
        for row in rendered_dict:
            if row.get("Report_Type") == self.event_display:
                target_row = row
                break

        assert "Signed_Off_By" in target_row.keys()
        assert ranger.name in target_row.get("Signed_Off_By")

        # Make sure dates get formatted properly and converted to system timezone
        assert target_row.get("Sample_Date_Time") == "2026-02-17 00:23"
