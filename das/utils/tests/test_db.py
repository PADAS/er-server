from unittest.mock import MagicMock

import pytest

from utils.db.connections import DatabaseConnectionCloser


class CustomException(Exception):
    pass


class TestUseSharedResourceUsageOnDatabaseConnectionCloser:
    def test_use_shared_resource_successfully(self):
        resource = MagicMock()
        resource_handler = DatabaseConnectionCloser(resource)

        resource_handler.close_connection()

        assert resource.inc_thread_sharing.called_once
        assert resource.close_if_unusable_or_obsolete.called_once
        assert resource.dec_thread_sharing.called_once

    def test_use_shared_resource_unsuccessfully(self):
        resource = MagicMock()
        resource.close_if_unusable_or_obsolete.side_effect = CustomException
        resource_handler = DatabaseConnectionCloser(resource)

        with pytest.raises(CustomException):
            resource_handler.close_connection()

        assert resource.inc_thread_sharing.called_once
        assert resource.close_if_unusable_or_obsolete.called_once
        assert resource.dec_thread_sharing.called_once
