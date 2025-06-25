from datetime import timedelta

import pytest
from psycopg2.extras import DateTimeTZRange

from django.utils import timezone

from das.factories import SourceFactory, TwoWayMessageProviderFactory
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectGroup, SubjectSource


@pytest.mark.django_db
class TestTwoWaySubjectSourceMixin:
    def test_get_two_way_sources_for_subject_source_without_children(self, subject_source, subject_group_empty):
        subject = subject_source.subject
        source = subject_source.source
        provider = source.provider
        subject_group_empty.subjects.add(subject)
        source.additional["two_way_messaging"] = True
        source.save()
        provider.additional["two_way_messaging"] = True
        provider.save()

        two_way_subject_source = TwoWaySubjectSourceMixin()
        queryset = SubjectGroup.objects.filter(id=subject_group_empty.id)
        two_way_subject_source._get_two_way_sources(queryset)

        source_data = two_way_subject_source.two_way_subject_sources.get(source.id)
        assert source_data is not None
        data = source_data.get(subject_source.id)
        assert data is not None

        assert source.id in two_way_subject_source.two_way_subject_sources.keys()
        assert subject_source.id in two_way_subject_source.two_way_subject_sources.get(source.id).keys()
        assert {
            "id",
            "subject_id",
            "source_id",
            "source__provider__display_name",
            "two_way_messaging",
            "source_two_way_messaging",
        } == two_way_subject_source.two_way_subject_sources.get(source.id).get(subject_source.id).keys()
        assert data.get("id") == subject_source.id
        assert data.get("subject_id") == subject.id
        assert data.get("source_id") == source.id
        assert data.get("source__provider__display_name") == provider.display_name
        assert data.get("two_way_messaging")
        assert data.get("source_two_way_messaging")

    def test_get_two_way_sources_for_subject_source_with_children(self, subject_source, subject_group_tree):
        subject = subject_source.subject
        source = subject_source.source
        provider = source.provider
        subject_group_tree.children.first().subjects.add(subject)
        source.additional["two_way_messaging"] = True
        source.save()
        provider.additional["two_way_messaging"] = True
        provider.save()

        two_way_subject_source = TwoWaySubjectSourceMixin()
        queryset = SubjectGroup.objects.filter(id=subject_group_tree.id)
        two_way_subject_source._get_two_way_sources(queryset)

        source_data = two_way_subject_source.two_way_subject_sources.get(source.id)
        assert source_data is not None
        data = source_data.get(subject_source.id)
        assert data is not None

        assert source.id in two_way_subject_source.two_way_subject_sources.keys()
        assert subject_source.id in two_way_subject_source.two_way_subject_sources.get(source.id).keys()
        assert {
            "id",
            "subject_id",
            "source_id",
            "source__provider__display_name",
            "two_way_messaging",
            "source_two_way_messaging",
        } == two_way_subject_source.two_way_subject_sources.get(source.id).get(subject_source.id).keys()
        assert data.get("id") == subject_source.id
        assert data.get("subject_id") == subject.id
        assert data.get("source_id") == source.id
        assert data.get("source__provider__display_name") == provider.display_name
        assert data.get("two_way_messaging")
        assert data.get("source_two_way_messaging")

    def test_get_two_way_sources_for_subject_with_multiple_sources_one_expired(self, subject_group_empty):
        # Create a subject
        subject = Subject.objects.create(name="Test Subject")
        subject_group_empty.subjects.add(subject)

        # Create two providers with two-way messaging enabled
        provider1 = TwoWayMessageProviderFactory(two_way_messaging=True)
        provider2 = TwoWayMessageProviderFactory(two_way_messaging=True)

        # Create two sources with two-way messaging enabled
        source1 = SourceFactory(provider=provider1)
        source2 = SourceFactory(provider=provider2)

        # Create an expired SubjectSource (assigned in the past)
        past_date = timezone.now() - timedelta(days=30)
        expired_range = DateTimeTZRange(lower=past_date - timedelta(days=1), upper=past_date)
        expired_subject_source = SubjectSource.objects.create(
            subject=subject, source=source1, assigned_range=expired_range
        )

        # Create an active SubjectSource (assigned now and into the future)
        current_date = timezone.now()
        active_range = DateTimeTZRange(lower=current_date - timedelta(days=1), upper=current_date + timedelta(days=365))
        active_subject_source = SubjectSource.objects.create(
            subject=subject, source=source2, assigned_range=active_range
        )

        # Verify the expired source is actually expired
        assert expired_subject_source.is_expired
        assert not active_subject_source.is_expired

        # Test the mixin
        two_way_subject_source = TwoWaySubjectSourceMixin()
        queryset = SubjectGroup.objects.filter(id=subject_group_empty.id)
        two_way_subject_source._get_two_way_sources(queryset)

        # Should only get the active source (source2)
        assert source2.id in two_way_subject_source.two_way_subject_sources.keys()
        assert source1.id not in two_way_subject_source.two_way_subject_sources.keys()

        # Verify the data for the active source
        source2_data = two_way_subject_source.two_way_subject_sources.get(source2.id)
        assert source2_data is not None
        active_data = source2_data.get(active_subject_source.id)
        assert active_data is not None
        assert active_data.get("id") == active_subject_source.id
        assert active_data.get("subject_id") == subject.id
        assert active_data.get("source_id") == source2.id
        assert active_data.get("source__provider__display_name") == provider2.display_name
        assert active_data.get("two_way_messaging")
