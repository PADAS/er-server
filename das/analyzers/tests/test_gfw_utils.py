from datetime import date

import pytest

from analyzers.gfw_utils import should_backfill_confirmed_alerts
from utils.features import features
from utils.tenant import Tenant


class TestUtils:
    @pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
    def test_should_backfill_comfirmed_alerts(self, tenant_response):
        tenant_settings = Tenant.from_dict(tenant_response)
        tenant_settings.feature_flags.gfw_back_fill_interval_days = True
        monkeypatch.setattr("das_server.views.get_tenant_settings", MagicMock(return_value=tenant_settings))

        should_it = should_backfill_confirmed_alerts(date(1955, 11, 5))

        assert should_it is True
