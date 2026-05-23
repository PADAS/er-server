import zoneinfo
from datetime import datetime, timedelta, timezone

import pytest
from faker import Faker

from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from factories import (
    SourceFactory,
    SubjectFactory,
    SubjectSourceFactory,
    SubjectSubTypeFactory,
    UserFactory,
)
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
        now = datetime.now(tz=timezone.utc)
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
        now = datetime.now(tz=timezone.utc)
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
        now = datetime.now(tz=timezone.utc)
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
        now = datetime.now(tz=timezone.utc)
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

        # Use zoneinfo for timezone-aware datetime, America/Los_Angeles is UTC-8 in December
        tz = zoneinfo.ZoneInfo("America/Los_Angeles")
        aware_dt = datetime(2020, 12, 20, 15, 45, 0, tzinfo=tz)
        observation.recorded_at = aware_dt
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

    @pytest.mark.parametrize(
        "full_manufacturer_id,expected_display_name",
        [
            ("88CE99DC88_EVG6q84wwjTqvYlPg00BF9EJpWK99zh6pAmRJ80j_A", "88CE99DC88"),
            ("XXXXXXX538_n987M6D7XGi42Q34OwAVcL7OOOygxncg8J1GrDE4_A", "XXXXXXX538"),
        ],
    )
    def test_buoy_gear_subject_parses_manufacturer_id_first_segment(
        self, das_tenant, full_manufacturer_id, expected_display_name
    ):
        """Test that buoy gear subjects parse the first segment of manufacturer_id as the name."""
        # Create a subject subtype for buoy gear
        buoy_subtype = SubjectSubTypeFactory(value=BUOY_GEAR_SUBJECT_SUBTYPE, das_tenant=das_tenant)

        # Create a subject with the buoy gear subtype
        subject = SubjectFactory(
            name="Original Subject Name",
            subject_subtype=buoy_subtype,
            das_tenant=das_tenant,
        )

        # Create a source with a manufacturer_id containing underscores
        source = SourceFactory(manufacturer_id=full_manufacturer_id, das_tenant=das_tenant)

        # Link the subject to the source
        SubjectSourceFactory(subject=subject, source=source, das_tenant=das_tenant)

        # Serialize the subject
        serialized_subject = SubjectSerializer(subject).data

        # The name should be only the first segment before the underscore
        assert serialized_subject["name"] == expected_display_name

    def test_buoy_gear_subject_uses_full_manufacturer_id_without_underscores(self, das_tenant):
        """Test that buoy gear subjects use full manufacturer_id when no underscores present."""
        # Create a subject subtype for buoy gear
        buoy_subtype = SubjectSubTypeFactory(value=BUOY_GEAR_SUBJECT_SUBTYPE, das_tenant=das_tenant)

        # Create a subject with the buoy gear subtype
        subject = SubjectFactory(
            name="Original Subject Name",
            subject_subtype=buoy_subtype,
            das_tenant=das_tenant,
        )

        # Create a source with a simple manufacturer_id (no underscores)
        manufacturer_id = "BUOY12345"
        source = SourceFactory(manufacturer_id=manufacturer_id, das_tenant=das_tenant)

        # Link the subject to the source
        SubjectSourceFactory(subject=subject, source=source, das_tenant=das_tenant)

        # Serialize the subject
        serialized_subject = SubjectSerializer(subject).data

        # The name should be the full manufacturer_id since there are no underscores
        assert serialized_subject["name"] == manufacturer_id

    def test_buoy_gear_subject_falls_back_to_name_when_no_source(self, das_tenant):
        """Test that buoy gear subjects fall back to subject name when no source is linked."""
        # Create a subject subtype for buoy gear
        buoy_subtype = SubjectSubTypeFactory(value=BUOY_GEAR_SUBJECT_SUBTYPE, das_tenant=das_tenant)

        # Create a subject with the buoy gear subtype but no linked source
        original_name = "Buoy Subject Without Source"
        subject = SubjectFactory(
            name=original_name,
            subject_subtype=buoy_subtype,
            das_tenant=das_tenant,
        )

        # Serialize the subject
        serialized_subject = SubjectSerializer(subject).data

        # The name should fall back to the original subject name
        assert serialized_subject["name"] == original_name

    def test_buoy_gear_subject_falls_back_when_manufacturer_id_is_empty(self, das_tenant):
        """Test that buoy gear subjects fall back to subject name when manufacturer_id is empty."""
        # Create a subject subtype for buoy gear
        buoy_subtype = SubjectSubTypeFactory(value=BUOY_GEAR_SUBJECT_SUBTYPE, das_tenant=das_tenant)

        # Create a subject with the buoy gear subtype
        original_name = "Buoy Subject With Empty Manufacturer"
        subject = SubjectFactory(
            name=original_name,
            subject_subtype=buoy_subtype,
            das_tenant=das_tenant,
        )

        # Create a source with no manufacturer_id
        source = SourceFactory(manufacturer_id=None, das_tenant=das_tenant)

        # Link the subject to the source
        SubjectSourceFactory(subject=subject, source=source, das_tenant=das_tenant)

        # Serialize the subject
        serialized_subject = SubjectSerializer(subject).data

        # The name should fall back to the original subject name
        assert serialized_subject["name"] == original_name

    def test_buoy_gear_subject_falls_back_when_manufacturer_id_invalid_pattern(self, das_tenant):
        """Test that buoy gear subjects fall back to subject name when manufacturer_id doesn't match pattern."""
        # Create a subject subtype for buoy gear
        buoy_subtype = SubjectSubTypeFactory(value=BUOY_GEAR_SUBJECT_SUBTYPE, das_tenant=das_tenant)

        # Create a subject with the buoy gear subtype
        original_name = "Buoy Subject With Invalid Pattern"
        subject = SubjectFactory(
            name=original_name,
            subject_subtype=buoy_subtype,
            das_tenant=das_tenant,
        )

        # Create a source with a manufacturer_id that doesn't match the expected pattern
        # (too short, contains special chars, etc.)
        source = SourceFactory(manufacturer_id="AB-12", das_tenant=das_tenant)

        # Link the subject to the source
        SubjectSourceFactory(subject=subject, source=source, das_tenant=das_tenant)

        # Serialize the subject
        serialized_subject = SubjectSerializer(subject).data

        # The name should fall back to the original subject name since pattern doesn't match
        assert serialized_subject["name"] == original_name

    def test_non_buoy_subject_uses_original_name(self, subject):
        """Test that non-buoy subjects still use their original name."""
        original_name = subject.name

        # Serialize the subject
        serialized_subject = SubjectSerializer(subject).data

        # The name should be the original subject name
        assert serialized_subject["name"] == original_name

    def test_buoy_gear_subject_uses_annotation_when_available(self, das_tenant):
        """Test that buoy gear subjects use the annotation for performance optimization."""
        from observations.models import Subject

        # Create a subject subtype for buoy gear
        buoy_subtype = SubjectSubTypeFactory(value=BUOY_GEAR_SUBJECT_SUBTYPE, das_tenant=das_tenant)

        # Create a subject with the buoy gear subtype
        subject = SubjectFactory(
            name="Original Subject Name",
            subject_subtype=buoy_subtype,
            das_tenant=das_tenant,
        )

        # Create a source with a manufacturer_id
        full_manufacturer_id = "88CE99DC88_EVG6q84wwjTqvYlPg00BF9EJpWK99zh6pAmRJ80j_A"
        expected_display_name = "88CE99DC88"
        source = SourceFactory(manufacturer_id=full_manufacturer_id, das_tenant=das_tenant)

        # Link the subject to the source
        SubjectSourceFactory(subject=subject, source=source, das_tenant=das_tenant)

        # Query with annotation (simulating what SubjectsView does)
        annotated_subject = Subject.objects.filter(id=subject.id).annotate_with_subjectsource_transforms().first()

        # Verify the annotation exists
        assert hasattr(annotated_subject, "latest_source_manufacturer_id")
        assert annotated_subject.latest_source_manufacturer_id == full_manufacturer_id

        # Serialize the annotated subject
        serialized_subject = SubjectSerializer(annotated_subject).data

        # The name should be parsed from the annotation
        assert serialized_subject["name"] == expected_display_name

    def test_buoy_gear_feature_props_returns_correct_data(self, das_tenant):
        """Test that _get_buoy_gear_feature_props returns correct name, additional, and device_status_properties."""
        # Create a subject subtype for buoy gear
        buoy_subtype = SubjectSubTypeFactory(value=BUOY_GEAR_SUBJECT_SUBTYPE, das_tenant=das_tenant)

        # Create a subject with the buoy gear subtype
        subject = SubjectFactory(
            name="Original Subject Name",
            subject_subtype=buoy_subtype,
            das_tenant=das_tenant,
        )

        # Create a source with a manufacturer_id and provider
        full_manufacturer_id = "88CE99DC88_EVG6q84wwjTqvYlPg00BF9EJpWK99zh6pAmRJ80j_A"
        expected_display_name = "88CE99DC88"
        source = SourceFactory(manufacturer_id=full_manufacturer_id, das_tenant=das_tenant)
        provider_display_name = source.provider.display_name

        # Link the subject to the source
        SubjectSourceFactory(subject=subject, source=source, das_tenant=das_tenant)

        # Test _get_buoy_gear_feature_props
        serializer = SubjectSerializer()
        device_status_props = [{"label": "test", "value": 123}]
        display_name, additional, returned_device_props = serializer._get_buoy_gear_feature_props(
            subject, device_status_props
        )

        # Check display_name (parsed manufacturer_id)
        assert display_name == expected_display_name

        # Check additional contains display_id and manufacturer
        assert additional["display_id"] == str(subject.id)
        assert additional["manufacturer"] == provider_display_name

        # Check device_status_properties is passed through
        assert returned_device_props == device_status_props

    def test_buoy_gear_feature_props_returns_none_for_non_buoy_subject(self, subject):
        """Test that _get_buoy_gear_feature_props returns None for non-buoy subjects."""
        serializer = SubjectSerializer()
        display_name, additional, device_props = serializer._get_buoy_gear_feature_props(subject, None)

        assert display_name is None
        assert additional is None
        assert device_props is None

    def test_provider_display_name_annotation(self, das_tenant):
        """Test that latest_source_provider_display_name annotation works correctly."""
        from observations.models import Subject

        # Create a subject subtype for buoy gear
        buoy_subtype = SubjectSubTypeFactory(value=BUOY_GEAR_SUBJECT_SUBTYPE, das_tenant=das_tenant)

        # Create a subject with the buoy gear subtype
        subject = SubjectFactory(
            name="Original Subject Name",
            subject_subtype=buoy_subtype,
            das_tenant=das_tenant,
        )

        # Create a source with a provider
        source = SourceFactory(
            manufacturer_id="TEST123_xyz",
            das_tenant=das_tenant,
        )
        expected_provider_name = source.provider.display_name

        # Link the subject to the source
        SubjectSourceFactory(subject=subject, source=source, das_tenant=das_tenant)

        # Query with annotation
        annotated_subject = Subject.objects.filter(id=subject.id).annotate_with_subjectsource_transforms().first()

        # Verify the annotation exists and has the correct value
        assert hasattr(annotated_subject, "latest_source_provider_display_name")
        assert annotated_subject.latest_source_provider_display_name == expected_provider_name


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
            "subject": {"name": source.subject.name, "id": str(source.subject.id)},
        }

        serializer = SourceSerializer(source, data=data, partial=True)
        if not serializer.is_valid():
            assert not serializer.errors
        serializer.save()
        source.refresh_from_db()

        assert str(source.subject.id) == data.get("subject").get("id")
        assert source.subject.name == data.get("subject").get("name")
