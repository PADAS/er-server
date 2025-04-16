import logging
import os
from typing import Tuple
from unittest.mock import MagicMock, call, patch

import pytest
from celery import signature

from django.db.utils import OperationalError
from django.test import TestCase

from das_server import celery
from utils.tenant.celery import (
    TENANT_TASK_NAME,
    OverAllTenantTask,
    TenantTask,
    run_by_single_tenant,
)

logger = logging.getLogger(__name__)


def get_module_and_task_names(task_path: Tuple) -> Tuple[str, str]:
    return task_path[1]["task"].rsplit(".", 1)


def get_args(task: Tuple):
    args = ()

    if "args" in task[1]:
        args = task[1]["args"]

    return args


def get_kwargs(task: Tuple):
    kwargs = {}

    if "kwargs" in task[1]:
        kwargs = task[1]["kwargs"]

    return kwargs


@celery.app.task(base=TenantTask)
def fake_tenant_test_task(*args, **kwargs):
    logger.info("In fake_tenant_test_task()")


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestTenantCeleryTasks:

    @pytest.mark.parametrize("domain", [[b"zoo.com", b"tenant1.example.com", b"tenant2.example.com"]])
    @patch("utils.tenant.celery.group")
    @patch("das.utils.tenant.celery.signature")
    def test_tenant_schedule_celery_task(
        self, mock_signature, mock_group, tenant_document_cache_client_mock, tenant, domain, caplog, monkeypatch
    ):
        caplog.set_level(logging.INFO)
        tenant_document_cache_client_mock.get_set_by_key.return_value = domain
        monkeypatch.setattr("observations.tasks.poll_news_gcs_bucket", MagicMock(return_value=tenant))
        monkeypatch.setitem(os.environ, "CLUSTER_NAME", "R2D2")
        monkeypatch.setitem(os.environ, "CLUSTER_NAMESPACE", "SPACE")

        for tenant in domain:
            run_by_single_tenant.apply(args={}, kwargs={"tenant_domain": tenant.decode("utf-8")}, task=TENANT_TASK_NAME)

            assert f"Running: {TENANT_TASK_NAME} for Tenant domain: {tenant.decode('utf-8')}" in caplog.text

    @patch("core.models.DASTenant.objects.get")
    def test_tenent_mixin_operational_error_exception(self, mock_das_tenant_db_operation):
        mock_das_tenant_db_operation.side_effect = OperationalError("Tenant db error")
        with patch.object(fake_tenant_test_task, "retry", autospec=True) as mock_retry:
            kwargs = {"domain": "zoo.com"}
            fake_tenant_test_task(**kwargs)
            mock_retry.assert_called_once()
            args, kwargs = mock_retry.call_args
            assert isinstance(kwargs.get("exc"), OperationalError)


class TestOverAllTenantTask(TestCase):
    @patch("utils.tenant.celery.get_current_cluster_domains")
    @patch("utils.tenant.celery.group")
    @patch("das.utils.tenant.celery.signature")
    def test_each_tenant_spawns_a_single_task(self, mock_signature, mock_group, mock_get_current_cluster_domains):
        mock_tenants = ["tenant1.example.com", "tenant2.example.com", "tenant3.example.com"]
        mock_get_current_cluster_domains.return_value = mock_tenants

        mock_group_instance = MagicMock()
        mock_group.return_value = mock_group_instance

        task = OverAllTenantTask()
        task()

        tasks_signatures = [
            signature(TENANT_TASK_NAME, args=(tenant_domain,), kwargs={}, immutable=True)
            for tenant_domain in mock_tenants
        ]

        expected_signature_calls = [call(tasks_signatures)]
        mock_group.assert_has_calls(expected_signature_calls)

        mock_group_instance.apply_async.assert_called_once()
