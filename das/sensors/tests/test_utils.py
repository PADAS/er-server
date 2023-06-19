import logging
from collections import OrderedDict
from datetime import datetime

import pytest

from observations.models import Subject, SubjectSource
from sensors.subject_name_change import mutate_ertrack_subject_assignment


@pytest.mark.django_db
class TestMutateErTrackSubjectAssignment:
    recorded_at = datetime.now()

    def test_use_linked_subject_to_user(self, ops_user, subject, source, caplog):
        caplog.set_level(logging.INFO)
        subject.linked_user = ops_user
        subject.save()
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)

        mutate_ertrack_subject_assignment(
            source=source, recorded_at=self.recorded_at, is_new_source=False, observation=observation
        )
        subject_source = SubjectSource.objects.get(source=source)

        assert Subject.objects.all().count() == 1
        assert "Updating source assignment using linked subject." in caplog.text
        assert subject_source.subject == subject

    def test_links_subject_without_linked_user_to_user_without_linked_subject(self, ops_user, subject, source, caplog):
        caplog.set_level(logging.INFO)
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)
        observation["subject_id"] = str(subject.id)

        mutate_ertrack_subject_assignment(
            source=source, recorded_at=self.recorded_at, is_new_source=False, observation=observation
        )
        subject_source = SubjectSource.objects.get(source=source)
        subject.refresh_from_db()

        assert f"Linking subject {subject.name} to user {ops_user.username}" in caplog.text
        assert subject.linked_user == ops_user
        assert subject_source.subject == subject

    def test_links_existing_subject_to_user_without_linked_subject_when_pass_subject_name(
        self, ops_user, superuser, subject_subtype, subject, source
    ):
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)
        observation["subject_name"] = str(subject.name)

        mutate_ertrack_subject_assignment(
            source=source,
            recorded_at=self.recorded_at,
            is_new_source=False,
            user=superuser,
            observation=observation,
            subject_name=subject.name,
            subject_subtype_id=subject_subtype,
        )
        subject_source = SubjectSource.objects.get(source=source)
        subject.refresh_from_db()

        assert subject_source.subject == subject
        assert subject.linked_user == ops_user

    def test_links_new_subject_to_user_that_was_created_because_the_sent_subject_is_already_linked_to_another_user(
        self, ops_user, superuser, subject, source, subject_subtype
    ):
        subject.linked_user = superuser
        subject.save()
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)
        observation["subject_name"] = str(subject.name)

        mutate_ertrack_subject_assignment(
            source=source,
            recorded_at=self.recorded_at,
            is_new_source=False,
            observation=observation,
            subject_name=subject.name,
            subject_subtype_id=subject_subtype,
        )

        assert Subject.objects.filter(name=subject.name).count() == 2

    def test_links_new_subject_to_user_without_linked_subject_when_pass_subject_name(
        self, ops_user, source, subject_subtype
    ):
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)
        observation["subject_name"] = "new-subject"

        mutate_ertrack_subject_assignment(
            source=source,
            recorded_at=self.recorded_at,
            is_new_source=False,
            observation=observation,
            subject_name="new-subject",
            subject_subtype_id=subject_subtype,
        )
        subject = Subject.objects.last()
        subject_source = SubjectSource.objects.filter(source=source, subject=subject)

        assert subject.name == "new-subject"
        assert subject_source.count() == 1
        assert subject.linked_user == ops_user
