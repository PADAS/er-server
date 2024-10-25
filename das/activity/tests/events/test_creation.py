import copy
import json
import logging
import tempfile
from datetime import datetime, timedelta

import pytest
import pytz
from django_multitenant.utils import set_current_tenant
from drf_extra_fields.geo_fields import PointField

from django.core.management import call_command
from django.urls import reverse
from django.utils import lorem_ipsum, timezone
from rest_framework import status
from rest_framework.fields import DateTimeField

from accounts.models.permissionset import Permission, PermissionSet
from accounts.serializers import UserDisplaySerializer
from activity import views
from activity.models import (
    Event,
    EventCategory,
    EventDetails,
    EventNote,
    EventProvider,
    EventSource,
    EventsourceEvent,
    EventType,
)
from activity.tests import schema_examples
from choices.models import Choice

from ..test_events import (
    ET_OTHER,
    all_permissions,
    eventsource_user_event_permissions,
    eventsource_user_permissions,
    guest_user_permissions,
    power_user_permissions,
    radio_room_user_permissions,
    reported_by_permission_set_id,
)

logger = logging.getLogger(__name__)


@pytest.mark.usefixtures("tenant_settings", "das_tenant")
@pytest.mark.django_db
class TestEventViewCreation:
    """Test event creation"""

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant, create_user, create_event):
        self.event_url = reverse("events")

        set_current_tenant(das_tenant)
        call_command("loaddata_with_tenant", "initial_eventdata")
        call_command("loaddata_with_tenant", "event_data_model")
        call_command("loaddata_with_tenant", "test_events_schema")

        self.no_perms_user = create_user(username="no_perms_user", email="das_no_perms_user@vulcan.com")
        self.guest_user = create_user(username="guest_user", email="das_guest_user@vulcan.com")
        self.radio_room_user = create_user(username="radio_room_user", email="das_radio_room@vulcan.com")
        self.power_user = create_user(username="power_user", email="das_power_user@vulcan.com")
        self.all_perms_user = create_user(username="all_perms_user", email="das_all_perms@vulcan.com")
        self.eventsource_user_no1 = create_user(
            username="eventsource_user_no1", email="eventsource_user_no1@tempuri.org"
        )
        self.eventsource_user_no2 = create_user(
            username="eventsource_user_no2", email="eventsource_user_no2@tempuri.org"
        )

        self.notes_line1_prefix = "note1 text"
        self.notes_line2_prefix = "note2 text"
        self.notes = [
            {"text": self.notes_line1_prefix + lorem_ipsum.paragraph()},
            {"text": self.notes_line2_prefix + lorem_ipsum.paragraph()},
        ]
        self.event_data = dict(
            title="Test Event",
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude=40.1353, latitude=-1.891517),
        )

        self.event_data_with_notes = copy.deepcopy(self.event_data)
        self.event_data_with_notes = copy.deepcopy(self.event_data)
        self.event_data_with_notes["notes"] = self.notes

        self.sample_event = create_event(self.event_data_with_notes)

        self.reported_by_permission_set = PermissionSet.objects.get(id=reported_by_permission_set_id)
        self.all_perms_permissionset = PermissionSet.objects.create(name="all_perms_set")
        self.can_export_data_permission_set = PermissionSet.objects.get(name="Can Export Data")

        for permission_name in all_permissions:
            self.all_perms_permissionset.permissions.add(
                Permission.objects.get_by_natural_key(codename=permission_name, app_label="activity", model="event")
            )
        self.all_perms_user.permission_sets.add(self.all_perms_permissionset)
        self.all_perms_user.permission_sets.add(self.reported_by_permission_set)
        self.all_perms_user.permission_sets.add(self.can_export_data_permission_set)

        self.power_user_permissionset = PermissionSet.objects.create(name="power_set")
        for permission_name in power_user_permissions:
            self.power_user_permissionset.permissions.add(
                Permission.objects.get_by_natural_key(codename=permission_name, app_label="activity", model="event")
            )
        self.power_user.permission_sets.add(self.power_user_permissionset)
        self.power_user.permission_sets.add(self.reported_by_permission_set)

        self.radio_room_user_permissionset = PermissionSet.objects.create(name="radio_room_perms_set")
        for permission_name in radio_room_user_permissions:
            self.radio_room_user_permissionset.permissions.add(
                Permission.objects.get_by_natural_key(codename=permission_name, app_label="activity", model="event")
            )
        self.radio_room_user.permission_sets.add(self.radio_room_user_permissionset)

        self.guest_user_permissionset = PermissionSet.objects.create(name="guest_set")
        for permission_name in guest_user_permissions:
            self.guest_user_permissionset.permissions.add(
                Permission.objects.get_by_natural_key(codename=permission_name, app_label="activity", model="event")
            )
        self.guest_user.permission_sets.add(self.guest_user_permissionset)

        self.eventsource_user_permissionset = PermissionSet.objects.create(name="eventsource_permissionset")
        for permission_name in eventsource_user_permissions:
            self.eventsource_user_permissionset.permissions.add(Permission.objects.get(codename=permission_name))
        for permission_name in eventsource_user_event_permissions:
            self.eventsource_user_permissionset.permissions.add(
                Permission.objects.get_by_natural_key(codename=permission_name, app_label="activity", model="event")
            )
        for u in (self.eventsource_user_no1, self.eventsource_user_no2):
            u.permission_sets.add(self.radio_room_user_permissionset)

        self.user_rep = UserDisplaySerializer().to_representation(self.guest_user)

        self.temporary_folder = tempfile.mkdtemp()
        self.now = datetime.now(tz=pytz.utc)
        self.start_of_today = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.end_of_today = self.start_of_today + timedelta(hours=23, minutes=59, seconds=59)
        self.view = views.EventView

        et_other = EventType.objects.filter(value=ET_OTHER).first()
        self.et_other_id = et_other.id

    @pytest.fixture
    def create_event(self):
        def _create_event(event_data, user=None):
            data = copy.deepcopy(event_data)
            if "time" in event_data:
                data["event_time"] = DateTimeField().to_internal_value(event_data["time"])
                del data["time"]
            if isinstance(event_data.get("event_type", None), str):
                data["event_type"] = EventType.objects.get_by_value(event_data["event_type"])

            if "location" in data:
                data["location"] = PointField().to_internal_value(data["location"])

            notes = None
            if "notes" in data:
                notes = data["notes"]
                del data["notes"]

            data["created_by_user"] = user if user else self.radio_room_user

            event = Event.objects.create_event(**data)
            if notes:
                for note in notes:
                    EventNote.objects.create_note(event=event, created_by_user=event.created_by_user, **note)

            return event

        return _create_event

    def test_return_new_contained_events(self, create_client_for_user):
        event_data = json.loads(
            """{"priority":0,"event_type":"incident_collection","message":"test parent message","title":"test parent title","contains":[{"message":"test contains message","title":"SIT-REP","event_type":"contact_rep","time":"2017-06-21 14:43","event_details":{},"priority":0,"reported_by":null},{"message":"second test contains message","title":"Other","event_type":"other","time":"2017-06-21 14:44","event_details":{},"priority":0,"reported_by":null}]}"""
        )
        client = create_client_for_user(self.all_perms_user)
        response = client.post(self.event_url, event_data)

        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data["contains"]) == len(event_data["contains"])
        assert response.data["contains"][0]["related_event"]["message"] == event_data["contains"][0]["message"]

    def test_event_without_event_type(self, create_client_for_user):
        event_data = {"message": "this has no event type", "priority": "200"}
        client = create_client_for_user(self.all_perms_user)
        response = client.post(self.event_url, event_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "event_type" in response.data[0][0], "Event type must be provided."

    def test_add_event_with_external_event_type(self, create_client_for_user):
        eventprovider = EventProvider.objects.create(display="Smart CSD Provider", owner=self.eventsource_user_no1)
        external_event_type = "smart-carcass"
        eventsource_data = {
            "external_event_type": external_event_type,
            "display": "DAS: Carcass",
            # 'event_type': 'carcass_rep',
            "additional": {"version": 0},
        }

        client = create_client_for_user(self.eventsource_user_no1)
        eventsources_url = reverse("eventsources-view", args=[str(eventprovider.id)])
        response = client.post(eventsources_url, eventsource_data)

        assert response.status_code == status.HTTP_201_CREATED

        eventsource_id = response.data["id"]

        # Establish category and event-type to associate with the source.
        event_category = EventCategory.objects.create(
            value="sample-event-category",
            display="Some display",
            ordernum=1,
        )

        event_type = EventType.objects.create(
            value="some-generic-event-type",
            display="Some event-type",
            category=event_category,
            default_priority=0,
            default_state="resolved",
            ordernum=1,
        )

        # Manual step here: Associate the new generic event type to the
        # EventSource
        EventSource.objects.filter(eventprovider_id=str(eventprovider.id), id=eventsource_id).update(
            event_type=event_type
        )

        external_event_id = "asdfioaasfseiuro11414sfa"
        # Create an event with an "External Event ID"
        event_title = "Some arbirtrary event title."
        event_timestamp = datetime(2018, 9, 8, 12, 5, 4, tzinfo=pytz.utc)
        sort_at = datetime(2018, 9, 8, 12, 5, 4, tzinfo=pytz.utc)
        event_data = {
            "event_details": {"attributes": [{"key": "a", "value": "1"}]},
            "external_event_type": external_event_type,
            "priority": 100,
            "title": event_title,
            "external_event_id": external_event_id,
            "eventsource": eventsource_id,
            "location": {"latitude": 39.4, "longitude": -117.5},
            "time": event_timestamp.isoformat(),
            "sort_at": sort_at.isoformat(),
        }

        response = client.post(self.event_url, event_data)

        assert response.status_code == status.HTTP_201_CREATED

        eselist = EventsourceEvent.objects.filter(eventsource_id=eventsource_id, external_event_id=external_event_id)

        assert eselist.count() == 1

        event = eselist[0].event

        assert event.sort_at == sort_at
        assert eselist[0].eventsource.external_event_type == external_event_type
        assert eselist[0].event.title == event_title

    def test_add_event_with_external_event_type_and_no_permissions(self, create_client_for_user):
        eventprovider = EventProvider.objects.create(display="Smart CSD Provider", owner=self.eventsource_user_no1)

        eventsource_data = {
            "external_event_type": "smart_carcass_report",
            "display": "DAS: Carcass",
            "event_type": "carcass_rep",
            "additional": {"version": 0},
        }

        client = create_client_for_user(self.eventsource_user_no1)
        event_sources_url = reverse("eventsources-view", args=[str(eventprovider.id)])
        response = client.post(event_sources_url, eventsource_data)

        assert response.status_code == status.HTTP_201_CREATED

        eventsource_id = response.data["id"]
        # Create an event with an "External Event ID"
        event_data = {
            "event_details": {"attributes": [{"key": "a", "value": "1"}]},
            "eventsource": eventsource_id,
            "priority": 100,
            "title": "Test External Event",
            "location": {"latitude": 1.4, "longitude": 37.5},
            "time": datetime.now(tz=pytz.utc).isoformat(),
        }

        client = create_client_for_user(self.eventsource_user_no2)
        response = client.post(self.event_url, event_data)

        # Expect 400 becausethe event_type is not pre-existent
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_add_duplicate_external_event_id(self, create_client_for_user):
        """
        Ensure that for a single EventProvider / EventSource, we're not able to add a duplicate event identified
        by external_event_id.
        :return:
        """

        eventprovider = EventProvider.objects.create(display="Smart CSD Provider", owner=self.eventsource_user_no1)

        external_event_type = "smart-carcass-report"
        eventsource_data = {
            "external_event_type": external_event_type,
            "display": "DAS: Carcass",
            "event_type": "carcass_rep",
            "additional": {"version": 0},
        }

        client = create_client_for_user(self.eventsource_user_no1)
        response = client.post(reverse("eventsources-view", args=[str(eventprovider.id)]), eventsource_data)

        assert response.status_code == status.HTTP_201_CREATED

        eventsource_id = response.data["id"]
        external_event_id = "abcdefgh-ijklmnop"
        # Create an event with an "External Event ID"
        event_title = "Some arbirtrary event title."
        event_data = {
            "event_details": {"attributes": [{"key": "a", "value": "1"}]},
            "external_event_type": external_event_type,
            "priority": 100,
            "title": event_title,
            "external_event_id": external_event_id,
            "eventsource": eventsource_id,
            "location": {"latitude": 38.4, "longitude": -116.5},
            "time": datetime.now(tz=pytz.utc).isoformat(),
        }

        response = client.post(self.event_url, event_data)

        assert response.status_code == status.HTTP_201_CREATED

        eselist = EventsourceEvent.objects.filter(eventsource_id=eventsource_id, external_event_id=external_event_id)

        assert eselist.count() == 1
        assert eselist[0].event.title == event_title
        assert eselist[0].eventsource.external_event_type == external_event_type

        # Add duplicate
        response = client.post(self.event_url, event_data)

        assert response.status_code == status.HTTP_409_CONFLICT

    def test_post_with_checkboxes(self, create_client_for_user):
        schema = schema_examples.WILDLIFE_SCHEMA_CHECKBOX
        event_type = self.sample_event.event_type
        event_type.schema = schema
        event_type.save()
        data = json.loads(
            '{"priority":0,"time":"2021-06-05T19:26:32.985Z","event_details":{"wildlifesightingrep_species":["bongo"],"wildlifesightingrep_numberanimals":1,"wildlifesightingrep_collared":["no"],"wildlifesightingrep_comments":"Some Comments"}}'
        )
        data["event_type"] = event_type.value

        client = create_client_for_user(self.all_perms_user)
        response = client.post(self.event_url, data)

        assert response.status_code == 201
        event_id = response.data["id"]

        event_detail_url = reverse("event-view", args=[event_id])
        response = client.get(event_detail_url)

        assert response.status_code == 200
        event_details = EventDetails.objects.get(event_id=event_id)
        assert isinstance(event_details.data["event_details"]["wildlifesightingrep_species"][0], str)

    def test_consistency_checkbox_value(self, create_client_for_user):
        Choice.objects.all().delete()
        Choice.objects.create(
            model=Choice.Field_Reports, field="wildlifesightingrep_species", value="buffalo", display="Buffalo"
        )
        Choice.objects.create(model=Choice.Field_Reports, field="yesno", value="yes", display="Yes")

        schema = schema_examples.WILDLIFE_SCHEMA_CHECKBOX
        event_type = self.sample_event.event_type
        event_type.schema = schema
        event_type.save()

        payload = {
            "event_type": event_type.value,
            "event_details": {
                "wildlifesightingrep_species": ["buffalo"],
                "wildlifesightingrep_collared": ["yes"],
                "wildlifesightingrep_numberanimals": "2",
            },
        }

        client = create_client_for_user(self.all_perms_user)
        response = client.post(self.event_url, payload)

        assert response.status_code == 201

        expected_result = {
            "event_details": {
                "wildlifesightingrep_species": ["buffalo"],
                "wildlifesightingrep_collared": ["yes"],
                "wildlifesightingrep_numberanimals": "2",
            }
        }

        actual_result = Event.objects.get(id=response.data.get("id")).event_details.first()
        assert expected_result == actual_result.data

    def test_create_event_with_only_create_permission(self, create_client_for_user):
        permission_set = PermissionSet.objects.create(name="Only create Events")
        permission = Permission.objects.get_by_natural_key(
            codename="analyzer_event_create", app_label="activity", model="event"
        )
        permission_set.permissions.add(permission)
        self.no_perms_user.permission_sets.add(permission_set)

        event_data = {"title": "test title", "event_type": "acoustic_detection"}
        client = create_client_for_user(self.no_perms_user)
        response = client.post(self.event_url, event_data)

        assert response.status_code == 201
        assert "id" in response.data
        assert len(response.data.keys()) == 1
