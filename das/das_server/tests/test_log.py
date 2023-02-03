import os
from unittest import mock

os.environ.setdefault("ROOT_LOGGING_LEVEL", "")

import das_server.log as log  # noqa: E402


@mock.patch.dict(os.environ, {"DJANGO_LOGGING_LEVEL": ""})
def test_empty_str_logging_level():
    default = "OUTOFTHISWORLD"
    assert default == log.env_default_on_empty_str("DJANGO_LOGGING_LEVEL", default)


@mock.patch.dict(os.environ, {"DJANGO_LOGGING_LEVEL": "INFO"})
def test_non_empty_str_logging_level():
    default = "OUTOFTHISWORLD"
    assert "INFO" == log.env_default_on_empty_str("DJANGO_LOGGING_LEVEL", default)


def test_logging_initialization():
    log.init_logging()
