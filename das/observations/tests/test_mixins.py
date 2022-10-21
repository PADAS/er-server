import pytest

from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import SubjectGroup


@pytest.mark.django_db
class TestTwoWaySubjectSourceMixin:
    def test_get_two_way_sources_for_subject_source_without_children(
        self, subject_source, subject_group_empty
    ):
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

        data = two_way_subject_source.two_way_subject_sources.get(source.id).get(
            subject_source.id
        )
        assert source.id in two_way_subject_source.two_way_subject_sources.keys()
        assert (
            subject_source.id
            in two_way_subject_source.two_way_subject_sources.get(source.id).keys()
        )
        assert {
            "id",
            "subject_id",
            "source_id",
            "source__provider__display_name",
            "two_way_messaging",
            "source_two_way_messaging",
        } == two_way_subject_source.two_way_subject_sources.get(source.id).get(
            subject_source.id
        ).keys()
        assert data.get("id") == subject_source.id
        assert data.get("subject_id") == subject.id
        assert data.get("source_id") == source.id
        assert data.get(
            "source__provider__display_name") == provider.display_name
        assert data.get("two_way_messaging")
        assert data.get("source_two_way_messaging")

    def test_get_two_way_sources_for_subject_source_with_children(
        self, subject_source, subject_group_tree
    ):
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

        data = two_way_subject_source.two_way_subject_sources.get(source.id).get(
            subject_source.id
        )
        assert source.id in two_way_subject_source.two_way_subject_sources.keys()
        assert (
            subject_source.id
            in two_way_subject_source.two_way_subject_sources.get(source.id).keys()
        )
        assert {
            "id",
            "subject_id",
            "source_id",
            "source__provider__display_name",
            "two_way_messaging",
            "source_two_way_messaging",
        } == two_way_subject_source.two_way_subject_sources.get(source.id).get(
            subject_source.id
        ).keys()
        assert data.get("id") == subject_source.id
        assert data.get("subject_id") == subject.id
        assert data.get("source_id") == source.id
        assert data.get(
            "source__provider__display_name") == provider.display_name
        assert data.get("two_way_messaging")
        assert data.get("source_two_way_messaging")
