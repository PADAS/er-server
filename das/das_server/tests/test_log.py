import os

os.environ.setdefault("ROOT_LOGGING_LEVEL", "")

import das_server.log as log  # noqa: E402


def test_empty_str_logging_level():
    log.init_logging()
