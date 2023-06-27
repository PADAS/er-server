import logging
from collections import OrderedDict
from datetime import datetime

import pytest

from observations.models import Subject, SubjectSource
from sensors.subject_name_change import HandlerERTrack


@pytest.mark.django_db
class TestMutateErTrackSubjectAssignment:
    recorded_at = datetime.now()

    def test_use_linked_subject_to_user(self, ops_user, superuser, subject, source, subject_subtype, caplog):
        ops_user.first_name = "Paul"
        ops_user.last_name = "McCartney"
        ops_user.save()
        caplog.set_level(logging.INFO)
        subject.linked_user = ops_user
        subject.save()
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)

        handler = HandlerERTrack(
            source=source,
            user=superuser,
            is_new_source=True,
            subject_name="",
            recorded_at=self.recorded_at,
            subject_subtype_id=subject_subtype,
            observation=observation,
        )
        handler.handle()
        subject_source = SubjectSource.objects.get(source=source)
        subject.refresh_from_db()

        assert Subject.objects.all().count() == 1
        assert "Updating source assignment using linked subject." in caplog.text
        assert subject_source.subject == subject
        assert subject.name == "Paul McCartney"
        assert f"Renaming subject {subject.id}." in caplog.text

    def test_links_subject_without_linked_user_to_user_without_linked_subject(
        self, ops_user, superuser, subject_subtype, subject, source, caplog
    ):
        caplog.set_level(logging.INFO)
        ops_user.first_name = "John"
        ops_user.last_name = "Lennon"
        ops_user.save()
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)
        observation["subject_id"] = str(subject.id)
        subject_name = subject.name

        handler = HandlerERTrack(
            source=source,
            user=superuser,
            is_new_source=True,
            subject_name="",
            recorded_at=self.recorded_at,
            subject_subtype_id=subject_subtype,
            observation=observation,
        )
        handler.handle()
        subject_source = SubjectSource.objects.get(source=source)
        subject.refresh_from_db()

        assert f"Linking subject {subject_name} to user {ops_user.username}" in caplog.text
        assert subject.linked_user == ops_user
        assert subject_source.subject == subject
        assert subject.name == "John Lennon"
        assert f"Renaming subject {subject.id}." in caplog.text

    def test_links_existing_subject_to_user_without_linked_subject_when_pass_subject_name(
        self, ops_user, superuser, subject_subtype, subject, source
    ):
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)
        observation["subject_name"] = str(subject.name)

        handler = HandlerERTrack(
            source=source,
            user=superuser,
            is_new_source=True,
            subject_name=subject.name,
            recorded_at=self.recorded_at,
            subject_subtype_id=subject_subtype,
            observation=observation,
        )
        handler.handle()
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

        handler = HandlerERTrack(
            source=source,
            user=superuser,
            is_new_source=True,
            subject_name="",
            recorded_at=self.recorded_at,
            subject_subtype_id=subject_subtype,
            observation=observation,
        )
        handler.handle()

        assert Subject.objects.filter(name=subject.name).count() == 1

    def test_links_new_subject_to_user_without_linked_subject_when_pass_subject_name(
        self, ops_user, superuser, source, subject_subtype, caplog
    ):
        caplog.set_level(logging.INFO)
        ops_user.first_name = "George"
        ops_user.last_name = "Harrison"
        ops_user.save()
        observation = OrderedDict()
        observation["user_id"] = str(ops_user.id)
        observation["subject_name"] = "new-subject"

        handler = HandlerERTrack(
            source=source,
            user=superuser,
            is_new_source=True,
            subject_name="",
            recorded_at=self.recorded_at,
            subject_subtype_id=subject_subtype,
            observation=observation,
        )
        handler.handle()
        subject = Subject.objects.last()
        subject_source = SubjectSource.objects.filter(source=source, subject=subject)
        subject.refresh_from_db()

        assert subject_source.count() == 1
        assert subject.linked_user == ops_user
        assert subject.name == "George Harrison"
        assert f"Renaming subject {subject.id}" in caplog.text
