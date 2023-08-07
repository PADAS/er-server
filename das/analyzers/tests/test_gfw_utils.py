from datetime import date

from analyzers.gfw_utils import should_backfill_confirmed_alerts


class TestUtils:
    def test_should_backfill_comfirmed_alerts(self, tenant_response, monkeypatch):
        should_it = should_backfill_confirmed_alerts(date(1955, 11, 5))

        assert should_it is False
