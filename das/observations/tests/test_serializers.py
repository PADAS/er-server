from datetime import datetime, timedelta

import pytest
import pytz

from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from factories import SubjectFactory, UserFactory
from observations.models import (STATIONARY_SUBJECT_VALUE, SubjectSource,
                                 SubjectType)
from observations.serializers import (SubjectSourceSerializer,
                                      SubjectTrackSerializer)


@pytest.mark.django_db
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

        subject_source_serialized = SubjectSourceSerializer(
            subject_source).data
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
        assert additional["comments"] == subject_source.additional.get(
            "comments")
        assert additional["chronofile"] == subject_source.additional.get(
            "chronofile")
        assert additional["data_status"] == subject_source.additional.get(
            "data_status")
        assert additional["data_stops_reason"] == subject_source.additional.get(
            "data_stops_reason"
        )
        assert additional["data_stops_source"] == subject_source.additional.get(
            "data_stops_source"
        )
        assert additional["data_starts_source"] == subject_source.additional.get(
            "data_starts_source"
        )
        assert additional["date_off_or_removed"] == subject_source.additional.get(
            "date_off_or_removed"
        )

    def test_subject_source_serializer_for_stationary_subject(self, subject_source):
        subject_type_stationary_object = SubjectType.objects.get(
            value=STATIONARY_SUBJECT_VALUE
        )
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

        subject_source_serialized = SubjectSourceSerializer(
            subject_source).data
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
        assert additional["comments"] == subject_source.additional.get(
            "comments")
        assert additional["chronofile"] == subject_source.additional.get(
            "chronofile")
        assert additional["data_status"] == subject_source.additional.get(
            "data_status")
        assert additional["data_stops_reason"] == subject_source.additional.get(
            "data_stops_reason"
        )
        assert additional["data_stops_source"] == subject_source.additional.get(
            "data_stops_source"
        )
        assert additional["data_starts_source"] == subject_source.additional.get(
            "data_starts_source"
        )
        assert additional["date_off_or_removed"] == subject_source.additional.get(
            "date_off_or_removed"
        )

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

    def test_create_subject_source_using_serializer_without_location(
        self, subject, source
    ):
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
        assert (
            subject_serialized["features"][0]["properties"]["subject_subtype"]
            == subject.subject_subtype.value
        )
        assert subject_serialized["features"][0]["properties"]["id"] == subject.id
        assert (
            subject_serialized["features"][0]["properties"]["stroke"] == subject.color
        )
        assert (
            subject.image_url
            in subject_serialized["features"][0]["properties"]["image"]
        )

    def test_serialized_format(self, subject_serialized):
        assert isinstance(subject_serialized["features"], list)
        assert len(subject_serialized["features"])
        assert isinstance(
            subject_serialized["features"][0]["properties"], dict)
        assert isinstance(
            subject_serialized["features"][0]["properties"]["title"], str)
