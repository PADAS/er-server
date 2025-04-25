import logging
from unittest.mock import MagicMock, call, patch

import pytest

from django.db.utils import OperationalError

from core.models.core import DASTenant
from das_server import celery
from utils.tenant.celery import TENANT_TASK_NAME, OverAllTenantTask, TenantTask
from utils.tenant.exceptions import TenantNotFoundException

logger = logging.getLogger(__name__)


@celery.app.task(base=TenantTask)
def fake_tenant_test_task(*args, **kwargs):
    logger.info("In fake_tenant_test_task()")


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestTenantCeleryTasks:
    @patch("utils.tenant.celery.TenantContextManager")
    def test_direct_tenant_execution(self, mock_tenant_context):
        """Test direct execution with tenant_domain parameter"""
        task = OverAllTenantTask()
        task.run = MagicMock()

        task(tenant_domain="test.com")

        mock_tenant_context.assert_called_with("test.com")
        task.run.assert_called_once()

    @patch("core.models.DASTenant.objects.get")
    def test_tenent_mixin_operational_error_exception(self, mock_das_tenant_db_operation):
        mock_das_tenant_db_operation.side_effect = OperationalError("Tenant db error")
        with patch.object(fake_tenant_test_task, "retry", autospec=True) as mock_retry:
            kwargs = {"domain": "zoo.com"}
            fake_tenant_test_task(**kwargs)
            mock_retry.assert_called_once()
            args, kwargs = mock_retry.call_args
            assert isinstance(kwargs.get("exc"), OperationalError)


class TestOverAllTenantTask:
    @patch("utils.tenant.celery.get_current_cluster_domains")
    @patch("utils.tenant.celery.signature")
    def test_spawns_task_per_tenant(self, mock_signature, mock_get_current_cluster_domains):
        mock_tenants = ["tenant1.example.com", "tenant2.example.com", "tenant3.example.com"]
        mock_get_current_cluster_domains.return_value = mock_tenants

        mock_sigs = [MagicMock() for _ in mock_tenants]
        mock_signature.side_effect = mock_sigs

        task = OverAllTenantTask()
        task.name = "fake_task_name"
        task()

        expected_calls = [
            call(
                TENANT_TASK_NAME,
                args=("fake_task_name", ()),
                kwargs={"task_kwargs": {"tenant_domain": tenant}},
                immutable=True,
            )
            for tenant in mock_tenants
        ]
        mock_signature.assert_has_calls(expected_calls)

        for mock_sig in mock_sigs:
            mock_sig.apply_async.assert_called_once()

    @patch("utils.tenant.celery.get_current_cluster_domains")
    def test_no_tenants_warning(self, mock_get_current_cluster_domains, caplog):
        caplog.set_level(logging.WARNING)
        mock_get_current_cluster_domains.return_value = []

        task = OverAllTenantTask()
        task()

        assert "No tenants found in cluster!" in caplog.text

    @patch("utils.tenant.celery.TenantContextManager")
    def test_tenant_not_found_handling(self, mock_tenant_context, caplog):
        mock_tenant_context.side_effect = DASTenant.DoesNotExist()
        task = OverAllTenantTask()
        task(tenant_domain="missing.com")

        assert "Tenant with domain missing.com missing in local DB" in caplog.text

        mock_tenant_context.side_effect = TenantNotFoundException()
        task = OverAllTenantTask()
        task(tenant_domain="missing.com")

        assert "Tenant with domain missing.com missing in TMS" in caplog.text
