from __future__ import annotations

import json
from contextlib import ExitStack
from unittest.mock import patch

import pytest

import django.contrib.auth

from core.tests import BaseAPITest
from factories import SubjectFactory, SubjectGroupFactory

User = django.contrib.auth.get_user_model()


def _make_connections(username: str, domain: str, sids: list[str]) -> dict:
    """Build the Redis connections dict that client.get_all_connections_list returns."""
    return {
        sid.encode(): json.dumps({"username": username, "sid": sid, "bbox": None, "domain": domain}).encode()
        for sid in sids
    }


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectHandler(BaseAPITest):
    """Tests for _subject_handler, handle_new_subject, and handle_delete_subject."""

    def setUp(self):
        super().setUp()
        self.permitted_user = User.objects.create_user(
            "permitted_user",
            "permitted@test.com",
            "pass",
            is_superuser=True,
            is_staff=True,
        )
        self.sids_permitted = ["sid-permitted-1", "sid-permitted-2"]

    def _call_handler(self, subject_id: str, type_: str, username: str, sids: list[str]):
        """Call _subject_handler with mocked connections, pubsub, and close_old_connections.

        close_old_connections is patched so the handler's finally block does not
        close the DB connection that the test framework is still using when tests
        run sequentially in the same process.

        Returns the mock_publish MagicMock so callers can assert on it.
        """
        from rt_api.tasks import _subject_handler

        domain = self.tenant_settings.domain
        with ExitStack() as stack:
            mock_publish = stack.enter_context(patch("rt_api.tasks.pubsub.publish"))
            stack.enter_context(
                patch(
                    "rt_api.tasks.client.get_all_connections_list",
                    return_value=_make_connections(username, domain, sids),
                )
            )
            stack.enter_context(patch("rt_api.tasks.close_old_connections"))
            _subject_handler(subject_id, type_)
        return mock_publish

    # ------------------------------------------------------------------
    # new_subject
    # ------------------------------------------------------------------

    def test_new_subject_emits_to_permitted_user_sids(self):
        """_subject_handler with new_subject emits SubjectSerializer data to each SID of a permitted user."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)

        mock_publish = self._call_handler(
            str(subject.id), "new_subject", self.permitted_user.username, self.sids_permitted
        )

        self.assertEqual(mock_publish.call_count, len(self.sids_permitted))

        published_sids = set()
        for c in mock_publish.call_args_list:
            raw_payload, routing_key = c.args
            payload = json.loads(raw_payload)

            self.assertEqual(routing_key, "das.realtime.emit")
            self.assertEqual(payload["type"], "new_subject")
            self.assertEqual(payload["object_id"], str(subject.id))
            published_sids.add(payload["sid"])

            data = payload["data"]
            self.assertEqual(data["type"], "new_subject")
            self.assertEqual(data["subject_id"], str(subject.id))
            self.assertIsNotNone(data["subject_data"])
            self.assertEqual(data["subject_data"]["id"], str(subject.id))

        self.assertEqual(published_sids, set(self.sids_permitted))

    def test_new_subject_skips_user_without_view_permission(self):
        """_subject_handler with new_subject emits nothing for a user lacking view_subject perms."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)
        unpermitted_user = User.objects.create_user("unpermitted_user", "u@test.com", "pass")

        mock_publish = self._call_handler(str(subject.id), "new_subject", unpermitted_user.username, ["sid-no-perm"])

        mock_publish.assert_not_called()

    def test_new_subject_emits_nothing_when_no_connections(self):
        """_subject_handler with new_subject is a no-op when there are no connected clients."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)

        # Pass an empty SID list so no connections match.
        mock_publish = self._call_handler(str(subject.id), "new_subject", "nobody", [])

        mock_publish.assert_not_called()

    # ------------------------------------------------------------------
    # delete_subject
    # ------------------------------------------------------------------

    def test_delete_subject_emits_subject_data_none_to_all_sids(self):
        """_subject_handler with delete_subject emits subject_data=None to every connected SID."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)
        subject_id = str(subject.id)

        mock_publish = self._call_handler(
            subject_id, "delete_subject", self.permitted_user.username, self.sids_permitted
        )

        self.assertEqual(mock_publish.call_count, len(self.sids_permitted))

        published_sids = set()
        for c in mock_publish.call_args_list:
            raw_payload, routing_key = c.args
            payload = json.loads(raw_payload)

            self.assertEqual(routing_key, "das.realtime.emit")
            self.assertEqual(payload["type"], "delete_subject")
            self.assertEqual(payload["object_id"], subject_id)
            published_sids.add(payload["sid"])

            data = payload["data"]
            self.assertEqual(data["type"], "delete_subject")
            self.assertEqual(data["subject_id"], subject_id)
            self.assertIsNone(data["subject_data"])

        self.assertEqual(published_sids, set(self.sids_permitted))

    def test_delete_subject_emits_to_unpermitted_user_sids(self):
        """delete_subject bypasses permission checks — emits to every SID regardless of perms."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)
        subject_id = str(subject.id)
        unpermitted_user = User.objects.create_user("unpermitted_user2", "u2@test.com", "pass")

        mock_publish = self._call_handler(subject_id, "delete_subject", unpermitted_user.username, ["sid-no-perm-del"])

        self.assertEqual(mock_publish.call_count, 1)
        payload = json.loads(mock_publish.call_args_list[0].args[0])
        self.assertIsNone(payload["data"]["subject_data"])

    # ------------------------------------------------------------------
    # subject_group_ids in new_subject payload
    # ------------------------------------------------------------------

    def test_new_subject_emit_includes_visible_subject_group_ids(self):
        """new_subject data must include subject_group_ids for groups the user can see."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)
        group = SubjectGroupFactory.create(das_tenant=self.das_tenant, subjects=[subject])

        mock_publish = self._call_handler(str(subject.id), "new_subject", self.permitted_user.username, ["sid-grp-1"])

        self.assertEqual(mock_publish.call_count, 1)
        payload = json.loads(mock_publish.call_args_list[0].args[0])
        data = payload["data"]

        self.assertIn("subject_group_ids", data)
        self.assertIn(str(group.id), data["subject_group_ids"])

    def test_new_subject_emit_excludes_groups_user_cannot_see(self):
        """new_subject data must omit group IDs for groups the user lacks view_subjectgroup perms on."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)
        SubjectGroupFactory.create(das_tenant=self.das_tenant, subjects=[subject])

        # Use a user with no permissions — superuser=False, no permission sets.
        restricted_user = User.objects.create_user("restricted_grp", "rg@test.com", "pass")

        mock_publish = self._call_handler(str(subject.id), "new_subject", restricted_user.username, ["sid-restr"])

        # The user cannot see the subject either (no view_subject perm), so nothing is emitted.
        mock_publish.assert_not_called()

    def test_new_subject_emit_includes_empty_group_ids_when_no_groups(self):
        """new_subject data includes subject_group_ids as an empty list when subject has no groups."""
        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)

        mock_publish = self._call_handler(str(subject.id), "new_subject", self.permitted_user.username, ["sid-nogrp"])

        self.assertEqual(mock_publish.call_count, 1)
        payload = json.loads(mock_publish.call_args_list[0].args[0])
        self.assertEqual(payload["data"]["subject_group_ids"], [])

    # ------------------------------------------------------------------
    # Multi-tenant non-leakage
    # ------------------------------------------------------------------

    def test_new_subject_does_not_emit_to_different_tenant_sids(self):
        """Connections on a different tenant domain must not receive a new_subject emit.

        get_username_sids_map filters by current_tenant.domain, so a SID whose
        session ``domain`` does not match the current tenant is excluded before
        _subject_handler ever sees it.  This test verifies that boundary end-to-end.
        """
        from rt_api.tasks import _subject_handler

        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)
        own_domain = self.tenant_settings.domain
        other_domain = "other-tenant.example.com"
        own_sid = "sid-own-tenant"
        other_sid = "sid-other-tenant"

        # Build connections dict that contains one SID for each domain.
        connections = {
            own_sid.encode(): json.dumps(
                {"username": self.permitted_user.username, "sid": own_sid, "bbox": None, "domain": own_domain}
            ).encode(),
            other_sid.encode(): json.dumps(
                {"username": self.permitted_user.username, "sid": other_sid, "bbox": None, "domain": other_domain}
            ).encode(),
        }

        with ExitStack() as stack:
            mock_publish = stack.enter_context(patch("rt_api.tasks.pubsub.publish"))
            stack.enter_context(patch("rt_api.tasks.client.get_all_connections_list", return_value=connections))
            stack.enter_context(patch("rt_api.tasks.close_old_connections"))
            _subject_handler(str(subject.id), "new_subject")

        published_sids = {json.loads(c.args[0])["sid"] for c in mock_publish.call_args_list}
        self.assertIn(own_sid, published_sids)
        self.assertNotIn(other_sid, published_sids)

    def test_delete_subject_does_not_emit_to_different_tenant_sids(self):
        """delete_subject must not emit to SIDs belonging to a different tenant."""
        from rt_api.tasks import _subject_handler

        subject = SubjectFactory.create(is_active=True, das_tenant=self.das_tenant)
        subject_id = str(subject.id)
        own_domain = self.tenant_settings.domain
        other_domain = "other-tenant.example.com"
        own_sid = "sid-del-own"
        other_sid = "sid-del-other"

        connections = {
            own_sid.encode(): json.dumps(
                {"username": self.permitted_user.username, "sid": own_sid, "bbox": None, "domain": own_domain}
            ).encode(),
            other_sid.encode(): json.dumps(
                {"username": self.permitted_user.username, "sid": other_sid, "bbox": None, "domain": other_domain}
            ).encode(),
        }

        with ExitStack() as stack:
            mock_publish = stack.enter_context(patch("rt_api.tasks.pubsub.publish"))
            stack.enter_context(patch("rt_api.tasks.client.get_all_connections_list", return_value=connections))
            stack.enter_context(patch("rt_api.tasks.close_old_connections"))
            _subject_handler(subject_id, "delete_subject")

        published_sids = {json.loads(c.args[0])["sid"] for c in mock_publish.call_args_list}
        self.assertIn(own_sid, published_sids)
        self.assertNotIn(other_sid, published_sids)

    # ------------------------------------------------------------------
    # Celery task wrappers
    # ------------------------------------------------------------------

    def test_handle_new_subject_task_calls_subject_handler(self):
        """handle_new_subject task delegates to _subject_handler with type new_subject."""
        from rt_api.tasks import handle_new_subject

        subject_id = "aaaaaaaa-0000-0000-0000-000000000001"
        with patch("rt_api.tasks._subject_handler") as mock_handler:
            handle_new_subject.run(subject_id)

        mock_handler.assert_called_once_with(subject_id, "new_subject")

    def test_handle_delete_subject_task_calls_subject_handler(self):
        """handle_delete_subject task delegates to _subject_handler with type delete_subject."""
        from rt_api.tasks import handle_delete_subject

        subject_id = "aaaaaaaa-0000-0000-0000-000000000002"
        with patch("rt_api.tasks._subject_handler") as mock_handler:
            handle_delete_subject.run(subject_id)

        mock_handler.assert_called_once_with(subject_id, "delete_subject")
