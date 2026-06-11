import logging
from unittest.mock import MagicMock, call, patch

import pytest

from django.db.utils import OperationalError

from core.models.core import DASTenant
from das_server import celery
from utils.tenant.celery import OverAllTenantTask, TenantTask
from utils.tenant.exceptions import TenantNotFoundException

logger = logging.getLogger(__name__)


@celery.app.task(base=TenantTask)
def fake_tenant_test_task(*args, **kwargs):
    logger.info("In fake_tenant_test_task()")


@celery.app.task(base=TenantTask)
def fake_tenant_test_task_raising_dastenant_missing(*args, **kwargs):
    raise DASTenant.DoesNotExist()


@celery.app.task(base=TenantTask)
def fake_tenant_test_task_raising_tenant_not_found(*args, **kwargs):
    raise TenantNotFoundException()


class _NoopTenantContextManager:
    """Stand-in for TenantContextManager whose enter/exit succeed, so the task
    body runs as if the tenant context was resolved correctly."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


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

    @patch("utils.tenant.celery.TenantContextManager")
    def test_mixin_skips_without_retry_when_dastenant_missing_locally(self, mock_tenant_context, caplog):
        caplog.set_level(logging.WARNING)
        mock_tenant_context.side_effect = DASTenant.DoesNotExist()
        with patch.object(fake_tenant_test_task, "retry", autospec=True) as mock_retry:
            fake_tenant_test_task(domain="missing.com")

            assert "exists in TMS but is missing from the local" in caplog.text
            assert "skipping task" in caplog.text
            mock_retry.assert_not_called()

    @patch("utils.tenant.celery.TenantContextManager")
    def test_mixin_skips_without_retry_when_tenant_not_found_in_tms(self, mock_tenant_context, caplog):
        caplog.set_level(logging.WARNING)
        mock_tenant_context.side_effect = TenantNotFoundException()
        with patch.object(fake_tenant_test_task, "retry", autospec=True) as mock_retry:
            fake_tenant_test_task(domain="missing.com")

            assert "could not be resolved to a tenant in TMS" in caplog.text
            assert "skipping task" in caplog.text
            mock_retry.assert_not_called()

    @patch("utils.tenant.celery.TenantContextManager", _NoopTenantContextManager)
    def test_mixin_propagates_dastenant_doesnotexist_from_task_body(self, caplog):
        """DASTenant.DoesNotExist raised by the task body (after the tenant
        context was entered) is a real failure and must propagate, not be
        swallowed with the TMS/local mismatch warning."""
        caplog.set_level(logging.WARNING)
        with patch.object(fake_tenant_test_task_raising_dastenant_missing, "retry", autospec=True) as mock_retry:
            with pytest.raises(DASTenant.DoesNotExist):
                fake_tenant_test_task_raising_dastenant_missing(domain="zoo.com")

            assert "core_dastenant / tms.domain mismatch" not in caplog.text
            assert "skipping task" not in caplog.text
            mock_retry.assert_not_called()

    @patch("utils.tenant.celery.TenantContextManager", _NoopTenantContextManager)
    def test_mixin_propagates_tenant_not_found_from_task_body(self, caplog):
        """TenantNotFoundException raised by the task body (after the tenant
        context was entered) must propagate, not be swallowed with the
        skip-without-retry warning."""
        caplog.set_level(logging.WARNING)
        with patch.object(fake_tenant_test_task_raising_tenant_not_found, "retry", autospec=True) as mock_retry:
            with pytest.raises(TenantNotFoundException):
                fake_tenant_test_task_raising_tenant_not_found(domain="zoo.com")

            assert "could not be resolved to a tenant in TMS" not in caplog.text
            assert "skipping task" not in caplog.text
            mock_retry.assert_not_called()


class TestOverAllTenantTask:
    @patch("utils.tenant.celery.get_current_cluster_domains")
    def test_dispatches_actual_task_per_tenant(self, mock_get_current_cluster_domains):
        """Fan-out dispatches the actual task (not by_single_tenant_task) per tenant."""
        mock_tenants = ["tenant1.example.com", "tenant2.example.com", "tenant3.example.com"]
        mock_get_current_cluster_domains.return_value = mock_tenants

        task = OverAllTenantTask()
        task.name = "fake_task_name"

        with patch.object(task, "apply_async") as mock_apply:
            task()

            # expires is derived from the QueueOnce default_timeout setting
            expected_expires = task.default_timeout
            expected_calls = [
                call(args=(), kwargs={"tenant_domain": tenant}, expires=expected_expires) for tenant in mock_tenants
            ]
            mock_apply.assert_has_calls(expected_calls)
            assert mock_apply.call_count == len(mock_tenants)

    @patch("utils.tenant.celery.get_current_cluster_domains")
    def test_no_tenants_warning(self, mock_get_current_cluster_domains, caplog):
        caplog.set_level(logging.WARNING)
        mock_get_current_cluster_domains.return_value = []

        task = OverAllTenantTask()
        task()

        assert "No tenants found in cluster!" in caplog.text

    @patch("utils.tenant.celery.TenantContextManager")
    def test_tenant_not_found_handling(self, mock_tenant_context, caplog):
        caplog.set_level(logging.DEBUG)
        mock_tenant_context.side_effect = DASTenant.DoesNotExist()
        task = OverAllTenantTask()
        task(tenant_domain="missing.com")

        assert "Tenant with domain missing.com missing in local DB" in caplog.text

        mock_tenant_context.side_effect = TenantNotFoundException()
        task = OverAllTenantTask()
        task(tenant_domain="missing.com")

        assert "Tenant with domain missing.com missing in TMS" in caplog.text

    @patch("utils.tenant.celery.TenantContextManager")
    def test_tenant_domain_not_passed_to_run(self, mock_tenant_context):
        """tenant_domain is consumed by __call__ and not leaked to run()."""
        task = OverAllTenantTask()
        task.run = MagicMock()

        task(tenant_domain="test.com", extra_kwarg="value")

        task.run.assert_called_once_with(extra_kwarg="value")

    def test_get_key_without_tenant_domain(self):
        """Lock key for parent (no tenant_domain) uses base behavior."""
        task = OverAllTenantTask()
        task.name = "my_app.tasks.example"
        task.run = lambda: None
        task.once = {"graceful": True}

        key = task.get_key(args=(), kwargs={})
        assert "tenant_domain" not in key
        assert "my_app.tasks.example" in key

    def test_get_key_with_tenant_domain(self):
        """Lock key includes tenant_domain, producing unique keys per tenant."""
        task = OverAllTenantTask()
        task.name = "my_app.tasks.example"
        task.run = lambda: None
        task.once = {"graceful": True}

        key_t1 = task.get_key(args=(), kwargs={"tenant_domain": "tenant1.com"})
        key_t2 = task.get_key(args=(), kwargs={"tenant_domain": "tenant2.com"})
        key_no_tenant = task.get_key(args=(), kwargs={})

        assert "tenant_domain-tenant1.com" in key_t1
        assert "tenant_domain-tenant2.com" in key_t2
        assert key_t1 != key_t2
        assert key_t1 != key_no_tenant

    def test_get_key_does_not_mutate_kwargs(self):
        """get_key must not mutate the original kwargs dict."""
        task = OverAllTenantTask()
        task.name = "my_app.tasks.example"
        task.run = lambda: None
        task.once = {"graceful": True}

        original_kwargs = {"tenant_domain": "test.com"}
        task.get_key(args=(), kwargs=original_kwargs)

        assert "tenant_domain" in original_kwargs
