import importlib
import logging
from typing import Tuple

import pytest

from das_server.celery import app
from utils.features import features


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


@pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is on")
@pytest.mark.django_db
@pytest.mark.parametrize("domain", [[b"tenant_domain1.com"]])
def test_tenant_schedule_celery_task(memory_store_client_mock, tenant_response, domain, caplog):
    caplog.set_level(logging.INFO)

    memory_store_client_mock.get_all_keys.return_value = domain

    for task in app.conf.beat_schedule.items():
        module_name, function_name = get_module_and_task_names(task)
        module = importlib.import_module(module_name)

        args = get_args(task)
        kwargs = get_kwargs(task)

        function = getattr(module, function_name)
        function.apply(args=args, kwargs=kwargs)
        assert f"Running: {module_name}.{function_name} for Tenant domain: {domain[0].decode('utf-8')}" in caplog.text
