from datetime import datetime, timedelta

import pytest
import pytz
from faker import Faker

from django.contrib.gis.geos import Point
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from factories import SubjectFactory, UserFactory
from observations.models import (
    STATIONARY_SUBJECT_VALUE,
    Observation,
    SubjectSource,
    SubjectType,
)
from observations.serializers import (
    FlattenObservationSerializer,
    ObservationSerializer,
    SourceSerializer,
    SubjectSerializer,
    SubjectSourceSerializer,
    SubjectTrackSerializer,
)

faker = Faker()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectSourceSerializer:
    def test_subject_source_serializer_no_stationary_subject(self, subject_source):
        subject_source.additional = {
            "comments": "comments",
            "chronofile": None,
            "data_status": "status",
            "data_stops_reason": "stop_reason",
            "data_stops_source": "stops_source",
            "data_starts_source": "starts_source",
            "date_off_or_removed": "off_or_remove",
        }
        now = datetime.now()
        subject_source.assigned_range = [now - timedelta(hours=1), now]
        subject_source.location = Point(-103.313486, 20.420935)
        subject_source.save()

        subject_source_serialized = SubjectSourceSerializer(subject_source).data
        additional = subject_source_serialized.get("additional", {})

        assert subject_source_serialized["id"] == str(subject_source.id)
        assert (
            subject_source_serialized["assigned_range"]["lower"]
            == subject_source.assigned_range.lower.astimezone().isoformat()
        )
        assert (
            subject_source_serialized["assigned_range"]["upper"]
            == subject_source.assigned_range.upper.astimezone().isoformat()
        )
        assert subject_source_serialized["subject"] == subject_source.subject.id
        assert subject_source_serialized["source"] == subject_source.source.id
        assert subject_source_serialized["location"] == None
        assert additional["comments"] == subject_source.additional.get("comments")
        assert additional["chronofile"] == subject_source.additional.get("chronofile")
        assert additional["data_status"] == subject_source.additional.get("data_status")
        assert additional["data_stops_reason"] == subject_source.additional.get("data_stops_reason")
        assert additional["data_stops_source"] == subject_source.additional.get("data_stops_source")
        assert additional["data_starts_source"] == subject_source.additional.get("data_starts_source")
        assert additional["date_off_or_removed"] == subject_source.additional.get("date_off_or_removed")

    def test_subject_source_serializer_for_stationary_subject(self, subject_source):
        subject_type_stationary_object = SubjectType.objects.get(value=STATIONARY_SUBJECT_VALUE)
        subject = subject_source.subject
        subject.subject_subtype.subject_type = subject_type_stationary_object
        subject.subject_subtype.save()
        subject_source.additional = {
            "comments": "comments",
            "chronofile": None,
            "data_status": "status",
            "data_stops_reason": "stop_reason",
            "data_stops_source": "stops_source",
            "data_starts_source": "starts_source",
            "date_off_or_removed": "off_or_remove",
        }
        now = datetime.now()
        subject_source.assigned_range = [now - timedelta(hours=1), now]
        subject_source.location = Point(-103.313486, 20.420935)
        subject_source.save()

        subject_source_serialized = SubjectSourceSerializer(subject_source).data
        additional = subject_source_serialized.get("additional", {})

        assert subject_source_serialized["id"] == str(subject_source.id)
        assert (
            subject_source_serialized["assigned_range"]["lower"]
            == subject_source.assigned_range.lower.astimezone().isoformat()
        )
        assert (
            subject_source_serialized["assigned_range"]["upper"]
            == subject_source.assigned_range.upper.astimezone().isoformat()
        )
        assert subject_source_serialized["subject"] == subject_source.subject.id
        assert subject_source_serialized["source"] == subject_source.source.id
        assert subject_source_serialized["location"] == {
            "latitude": subject_source.location.y,
            "longitude": subject_source.location.x,
        }
        assert additional["comments"] == subject_source.additional.get("comments")
        assert additional["chronofile"] == subject_source.additional.get("chronofile")
        assert additional["data_status"] == subject_source.additional.get("data_status")
        assert additional["data_stops_reason"] == subject_source.additional.get("data_stops_reason")
        assert additional["data_stops_source"] == subject_source.additional.get("data_stops_source")
        assert additional["data_starts_source"] == subject_source.additional.get("data_starts_source")
        assert additional["date_off_or_removed"] == subject_source.additional.get("date_off_or_removed")

    def test_create_subject_source_using_serializer(self, subject, source):
        data = {
            "assigned_range": {
                "lower": "2022-03-31T17:00:00-07:00",
                "upper": "2022-05-15T16:59:59-07:00",
            },
            "source": source.id,
            "subject": subject.id,
            "additional": {},
            "location": {"latitude": 20.420935, "longitude": -103.313486},
        }

        serializer = SubjectSourceSerializer(data=data)
        serializer.is_valid()
        serializer.save()

        assert SubjectSource.objects.count() == 1

    def test_create_subject_source_using_serializer_without_location(self, subject, source):
        data = {
            "assigned_range": {
                "lower": "2022-03-31T17:00:00-07:00",
                "upper": "2022-05-15T16:59:59-07:00",
            },
            "source": source.id,
            "subject": subject.id,
            "additional": {},
        }

        serializer = SubjectSourceSerializer(data=data)
        serializer.is_valid()
        serializer.save()

        assert SubjectSource.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectTrackSerializer:
    @pytest.fixture()
    def subject(self):
        return SubjectFactory()

    @pytest.fixture()
    def subject_serialized(self, subject):
        factory = APIRequestFactory()
        url = reverse("subject-view-tracks", kwargs={"subject_id": subject.id})
        request = factory.get(url)
        request.user = UserFactory(is_superuser=True)
        now = pytz.utc.localize(datetime.utcnow())
        context = {
            "tracks_since": now - timedelta(days=5),
            "tracks_until": now,
            "tracks_limit": 2,
            "request": request,
        }
        return SubjectTrackSerializer(subject, context=context).data

    def test_serialized_fields(self, subject_serialized, subject):
        assert "features" in subject_serialized
        assert "properties" in subject_serialized["features"][0]
        assert subject_serialized["features"][0]["type"] == "Feature"
        assert subject_serialized["features"][0]["properties"]["title"] == subject.name
        assert (
            subject_serialized["features"][0]["properties"]["subject_type"]
            == subject.subject_subtype.subject_type.value
        )
        assert subject_serialized["features"][0]["properties"]["subject_subtype"] == subject.subject_subtype.value
        assert subject_serialized["features"][0]["properties"]["id"] == subject.id
        assert subject_serialized["features"][0]["properties"]["stroke"] == subject.color
        assert subject.image_url in subject_serialized["features"][0]["properties"]["image"]

    def test_serialized_format(self, subject_serialized):
        assert isinstance(subject_serialized["features"], list)
        assert len(subject_serialized["features"])
        assert isinstance(subject_serialized["features"][0]["properties"], dict)
        assert isinstance(subject_serialized["features"][0]["properties"]["title"], str)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestObservationSerializer:
    @pytest.mark.parametrize("coordinates", [(0, 0), (-103.313486, 20.420935)])
    def test_serialized_observation(self, subject_source, coordinates):
        source = subject_source.source
        provider = subject_source.source.provider
        provider.transforms = [
            {"dest": "voltage", "label": "voltage", "units": "v", "source": "voltage"},
            {"dest": "altitude", "label": "altitude", "units": "feet", "source": "altitude"},
        ]
        provider.save()
        now = timezone.now()
        point = Point(coordinates)
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": {"voltage": 10, "altitude": 20},
        }
        representation = {
            "source_id": "af1402d7-ad60-41ec-a69f-44461cb32141",
            "source_transforms": [{"dest": "speed", "label": "speed", "source": "speed", "units": "km"}],
            "additional": {"speed": 10},
            "location": point,
        }
        observation = Observation.objects.create(**data)

        serialized_observation = ObservationSerializer(observation)
        serialized_observation_data = serialized_observation.data
        serialized_dict_representation = serialized_observation.dict_to_representation(
            representation, {"include_details": True}
        )

        assert serialized_observation_data["id"] == str(observation.id)
        assert serialized_observation_data["location"] == {
            "latitude": float(coordinates[1]),
            "longitude": float(coordinates[0]),
        }
        assert serialized_observation_data["recorded_at"] == now.astimezone().isoformat()
        assert serialized_observation_data["created_at"] == observation.created_at.astimezone().isoformat()
        assert serialized_observation_data["source"] == str(source.id)
        assert serialized_dict_representation["source"] == representation.get("source")
        assert serialized_dict_representation["device_status_properties"] == [
            {"value": 10, "label": "speed", "units": "km"}
        ]
        assert serialized_dict_representation["observation_details"] == representation.get("observation_details")
        assert serialized_dict_representation["location"] == {
            "longitude": representation.get("location").get("longitude"),
            "latitude": representation.get("location").get("latitude"),
        }


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestFlattenObservationSerializer:
    def test_serialized_observation_format(self, observation):
        serialized_observation = FlattenObservationSerializer(observation).data

        assert isinstance(serialized_observation["coordinates"], list)
        assert isinstance(serialized_observation["time"], str)

    def test_serialized_observation(self, observation):
        observation.recorded_at = datetime(2020, 12, 20, 15, 45, 0)
        observation.location = Point(-103.313486, 20.420935)
        observation.save()

        serialized_observation = FlattenObservationSerializer(observation).data

        assert serialized_observation["coordinates"] == [-103.313486, 20.420935]
        assert serialized_observation["time"] == "2020-12-20T15:45:00-08:00"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectSerializer:
    def test_with_linked_user(self, subject, ops_user):
        subject.linked_user = ops_user
        subject.save()

        serialized_subject = SubjectSerializer(subject).data

        assert serialized_subject["user"]["id"] == str(ops_user.id)

    def test_without_linked_user(self, subject):
        serialized_subject = SubjectSerializer(subject).data

        assert not serialized_subject["user"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourceSerializer:
    def test_updating_an_existing_source(self, source):

        data = {"model_name": "new model"}

        serializer = SourceSerializer(source, data=data, partial=True)
        if not serializer.is_valid():
            assert not serializer.errors

        serializer.save()

        source.refresh_from_db()

        assert source.model_name == data["model_name"]

    def test_creating_a_source(self, source_provider):
        data = {
            "manufacturer_id": "111111",
            "provider": source_provider.provider_key,
            "source_type": "tracking-device",
            "additional": {"collar_id": "1234"},
            "model_name": faker.name(),
        }

        serializer = SourceSerializer(data=data)
        if not serializer.is_valid():
            assert not serializer.errors
        serializer.save()

    def test_creating_a_source_with_subject(self, source):
        source.subject = SubjectFactory()
        source.subject.save()
        
        data = {
            "manufacturer_id": "111111",
            "provider": source.provider.provider_key,
            "source_type": "tracking-device",
            "additional": {"collar_id": "1234"},
            "model_name": faker.name(),
            "subject": {"name": source.subject.name, "id": str(source.subject.id)}
        }

        serializer = SourceSerializer(source, data=data, partial=True)
        if not serializer.is_valid():
            assert not serializer.errors
        serializer.save()
        source.refresh_from_db()

        assert str(source.subject.id) == data.get("subject").get("id")
        assert source.subject.name == data.get("subject").get("name")
