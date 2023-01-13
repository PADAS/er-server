from unittest.mock import MagicMock

import pytest

from django.core.management import call_command


@pytest.mark.django_db
class TestCommands:
    def test_call_site_metrics(self, monkeypatch):
        site_metrics_mock = MagicMock(return_value=None)
        monkeypatch.setattr("das_server.management.commands.site_metrics.Command.handle", site_metrics_mock)

        call_command("site_metrics")

        site_metrics_mock.assert_called_once()
