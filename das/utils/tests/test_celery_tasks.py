import importlib
import logging
import os
from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest

from django.db.utils import OperationalError

from das_server import celery
from das_server.celery import app
from utils.tenant.celery import OverAllTenantTask, TenantTask

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

    @pytest.mark.parametrize("domain", [[b"zoo.com"]])
    def test_tenant_schedule_celery_task(self, tenant_document_cache_client_mock, tenant, domain, caplog, monkeypatch):
        caplog.set_level(logging.INFO)
        tenant_document_cache_client_mock.get_set_by_key.return_value = domain
        monkeypatch.setattr("tracking.tasks.get_tenant_settings", MagicMock(return_value=tenant))
        monkeypatch.setitem(os.environ, "CLUSTER_NAME", "R2D2")
        monkeypatch.setitem(os.environ, "CLUSTER_NAMESPACE", "SPACE")

        for task in app.conf.beat_schedule.items():
            module_name, function_name = get_module_and_task_names(task)
            module = importlib.import_module(module_name)

            args = get_args(task)
            kwargs = get_kwargs(task)

            function = getattr(module, function_name)

            if not isinstance(function, OverAllTenantTask):
                continue

            function.apply(args=args, kwargs=kwargs)
            assert (
                f"Running: {module_name}.{function_name} for Tenant domain: {domain[0].decode('utf-8')}" in caplog.text
            )

    @patch("core.models.DASTenant.objects.get")
    def test_tenent_mixin_operational_error_exception(self, mock_das_tenant_db_operation):
        mock_das_tenant_db_operation.side_effect = OperationalError("Tenant db error")
        with patch.object(fake_tenant_test_task, "retry", autospec=True) as mock_retry:
            kwargs = {"domain": "zoo.com"}
            fake_tenant_test_task(**kwargs)
            mock_retry.assert_called_once()
            args, kwargs = mock_retry.call_args
            assert isinstance(kwargs.get("exc"), OperationalError)
