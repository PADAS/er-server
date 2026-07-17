from __future__ import annotations

from unittest.mock import patch

import pytest

from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.tests import BaseAPITest
from factories import SubjectFactory
from observations.models import Subject
from observations.signals import subject_pre_save


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectPubsubSignals(BaseAPITest):
    """Test that Subject save/delete signals publish the correct pubsub messages."""

    def test_creating_active_subject_publishes_new_subject(self):
        """Creating a subject with is_active=True publishes das.subject.new on commit."""
        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)

        calls = [c for c in mock_publish.call_args_list if c.args[1] == "das.subject.new"]
        self.assertEqual(len(calls), 1)
        payload, routing_key = calls[0].args
        self.assertEqual(routing_key, "das.subject.new")
        self.assertEqual(payload["subject_id"], str(subject.id))

    def test_creating_inactive_subject_does_not_publish(self):
        """Creating a subject with is_active=False must NOT publish das.subject.new."""
        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                SubjectFactory.create(is_active=False, das_tenant=self.das_tenant)

        subject_new_calls = [c for c in mock_publish.call_args_list if c.args[1] == "das.subject.new"]
        self.assertEqual(subject_new_calls, [])

    def test_deactivating_subject_publishes_delete_subject(self):
        """Flipping is_active True→False on a saved subject publishes das.subject.delete on commit."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)

        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject.is_active = False
                subject.save()

        calls = [c for c in mock_publish.call_args_list if c.args[1] == "das.subject.delete"]
        self.assertEqual(len(calls), 1)
        payload, routing_key = calls[0].args
        self.assertEqual(routing_key, "das.subject.delete")
        self.assertEqual(payload["subject_id"], str(subject.id))

    def test_reactivating_subject_publishes_new_subject(self):
        """Flipping is_active False→True on a saved subject publishes exactly one das.subject.new
        and no das.subject.delete — the client re-inserts the subject via the new_subject handler."""
        subject = SubjectFactory.create(is_active=False, das_tenant=self.das_tenant)

        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject.is_active = True
                subject.save()

        new_calls = [c for c in mock_publish.call_args_list if c.args[1] == "das.subject.new"]
        delete_calls = [c for c in mock_publish.call_args_list if c.args[1] == "das.subject.delete"]

        self.assertEqual(len(new_calls), 1)
        self.assertEqual(new_calls[0].args[0]["subject_id"], str(subject.id))
        self.assertEqual(delete_calls, [])

    def test_activating_subject_created_inactive_publishes_new_subject(self):
        """A subject that was created inactive and then activated publishes das.subject.new."""
        subject = SubjectFactory.create(is_active=False, das_tenant=self.das_tenant)

        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject.is_active = True
                subject.save()

        new_calls = [c for c in mock_publish.call_args_list if c.args[1] == "das.subject.new"]
        self.assertEqual(len(new_calls), 1)
        self.assertEqual(new_calls[0].args[0]["subject_id"], str(subject.id))

    def test_noop_update_does_not_publish_subject_events(self):
        """A save that changes neither is_active nor creation must not publish new/delete subject events."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)

        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject.name = "Updated Name"
                subject.save()

        subject_calls = [
            c for c in mock_publish.call_args_list if c.args[1] in ("das.subject.new", "das.subject.delete")
        ]
        self.assertEqual(subject_calls, [])

    def test_updating_already_inactive_subject_does_not_publish_delete(self):
        """Saving a subject that was already inactive must not re-publish das.subject.delete."""
        subject = SubjectFactory.create(is_active=False, das_tenant=self.das_tenant)

        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject.name = "Another Update"
                subject.save()

        subject_calls = [
            c for c in mock_publish.call_args_list if c.args[1] in ("das.subject.new", "das.subject.delete")
        ]
        self.assertEqual(subject_calls, [])

    def test_reused_instance_does_not_spuriously_republish_delete_on_unrelated_save(self):
        """Regression: saving unrelated fields on a reused instance after deactivation must not
        re-publish das.subject.delete.

        Scenario (the reviewer's bug):
        1. subject.is_active = False; subject.save()  → publishes das.subject.delete once.
        2. subject.name = "x"; subject.save(update_fields=["name"])  → must publish nothing.

        Without the fix, _prev_is_active stays True from step 1 while is_active is already
        False, so step 2 spuriously triggers the delete branch a second time.
        """
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)

        # Step 1: deactivate — expect exactly one das.subject.delete.
        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject.is_active = False
                subject.save()

        delete_calls_after_deactivation = [c for c in mock_publish.call_args_list if c.args[1] == "das.subject.delete"]
        self.assertEqual(len(delete_calls_after_deactivation), 1)

        # Step 2: update an unrelated field on the SAME instance — expect zero new events.
        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject.name = "updated_name"
                subject.save(update_fields=["name"])

        subject_calls = [
            c for c in mock_publish.call_args_list if c.args[1] in ("das.subject.new", "das.subject.delete")
        ]
        self.assertEqual(subject_calls, [])

    def test_pre_save_skips_snapshot_query_for_new_instance(self):
        """subject_pre_save must not run the is_active snapshot SELECT for a new (adding) instance.

        Subject.id has a UUID default, so instance.pk is already populated before the
        first save; the guard therefore keys on _state.adding, not pk. This exercises
        the create path (including auto-provisioned subjects in sensor ingest) where
        there is no prior row to snapshot.
        """
        subject = SubjectFactory.build(is_active=True, das_tenant=self.das_tenant)
        self.assertTrue(subject._state.adding)
        self.assertIsNotNone(subject.pk)

        with CaptureQueriesContext(connection) as ctx:
            subject_pre_save(sender=Subject, instance=subject)

        self.assertEqual(len(ctx.captured_queries), 0)
        self.assertFalse(hasattr(subject, "_prev_is_active"))

    def test_hard_delete_publishes_das_subject_delete(self):
        """Hard-deleting a subject (instance.delete()) publishes das.subject.delete on commit."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)
        subject_id = str(subject.id)

        with patch("observations.signals.pubsub.publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                subject.delete()

        calls = [c for c in mock_publish.call_args_list if c.args[1] == "das.subject.delete"]
        self.assertEqual(len(calls), 1)
        payload, routing_key = calls[0].args
        self.assertEqual(routing_key, "das.subject.delete")
        self.assertEqual(payload["subject_id"], subject_id)
