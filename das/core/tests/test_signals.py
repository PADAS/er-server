import logging
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from django.test import override_settings

from core.models import DASTenant


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCoreSignals:
    def test_post_save_tenant_signal_triggers_on_new_tenant(self, caplog, monkeypatch):
        caplog.set_level(logging.INFO)
        transaction_mock = MagicMock()
        pubsub_mock = MagicMock()
        monkeypatch.setattr("core.signals.transaction", transaction_mock)
        monkeypatch.setattr("core.signals.pubsub", pubsub_mock)

        DASTenant.objects.create(
            id="620ff24b-f11e-4c02-848f-81ee6fa08665",
            domain="new-tenant-domain.com",
        )

        assert f"saved tenant 620ff24b-f11e-4c02-848f-81ee6fa08665" in caplog.text
        transaction_mock.on_commit.assert_called_once()
        callback = transaction_mock.on_commit.call_args_list[0][0][0]
        callback()
        pubsub_mock.publish.assert_called_once_with(
            {"tenant_id": "620ff24b-f11e-4c02-848f-81ee6fa08665"}, "das.tenant.new"
        )

    def test_post_save_tenant_signal_triggers_on_update_tenant(self, caplog, monkeypatch, das_tenant):
        caplog.set_level(logging.INFO)
        transaction_mock = MagicMock()
        pubsub_mock = MagicMock()
        monkeypatch.setattr("core.signals.transaction", transaction_mock)
        monkeypatch.setattr("core.signals.pubsub", pubsub_mock)

        das_tenant.domain = "foo.pamdas.org"
        das_tenant.save()

        assert f"saved tenant {das_tenant.pk}" in caplog.text
        transaction_mock.on_commit.assert_called_once()
        callback = transaction_mock.on_commit.call_args_list[0][0][0]
        callback()
        pubsub_mock.publish.assert_called_once_with({"tenant_id": str(das_tenant.id)}, "das.tenant.update")

    @override_settings(ALLOWED_HOSTS=["localhost"])
    def test_post_save_tenant_signal_updates_allowed_hosts_setting(self, monkeypatch):
        transaction_mock = MagicMock()
        get_tenant_domains_mock = MagicMock()
        get_tenant_domains_mock.return_value = ["test-tenant.pamdas.org"]
        monkeypatch.setattr("core.signals.transaction", transaction_mock)
        monkeypatch.setattr("utils.tenant.domains.get_current_cluster_domains", get_tenant_domains_mock)

        new_das_tenant = DASTenant.objects.create(id=uuid4(), domain="test-tenant.pamdas.org")
        from django.conf import settings

        assert all(hostname in settings.ALLOWED_HOSTS for hostname in ["localhost", "test-tenant.pamdas.org"])
