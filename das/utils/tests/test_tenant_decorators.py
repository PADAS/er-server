from unittest.mock import Mock, patch

import pytest

from django.http import HttpResponse

from utils.tenant.decorators import (
    IdpNotConfiguredError,
    assert_idp_configured,
    require_enabled_idp_configs,
)


@pytest.fixture()
def mock_tenant_settings():
    mock = Mock()
    mock.id = "test-tenant-id"
    mock.feature_flags.require_idp = True
    with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock):
        yield mock


class TestAssertIdpConfigured:

    def test_passes_when_both_flags_set(self, mock_tenant_settings):
        assert_idp_configured()

    @pytest.mark.parametrize("falsy_value", [False, None, 0])
    def test_raises_when_require_idp_falsy(self, mock_tenant_settings, falsy_value):
        mock_tenant_settings.feature_flags.require_idp = falsy_value
        with pytest.raises(IdpNotConfiguredError, match=r"^tenant test-tenant-id: require_idp is not enabled$"):
            assert_idp_configured()


class TestRequireEnabledIdpConfigs:

    def test_allows_request_when_configured(self, mock_tenant_settings):
        @require_enabled_idp_configs(message="Nope.", status=400)
        def view(_):
            return HttpResponse("ok")

        result = view("fake_request")

        assert result.status_code == 200
        assert result.content == b"ok"

    @pytest.mark.parametrize(
        "flag, falsy_value",
        [
            ("require_idp", False),
            ("require_idp", None),
            ("require_idp", 0),
        ],
    )
    def test_blocks_request_with_message_and_status(self, mock_tenant_settings, flag, falsy_value):
        setattr(mock_tenant_settings.feature_flags, flag, falsy_value)
        view_called = False

        @require_enabled_idp_configs(message="Custom error.", status=403)
        def view(_):
            nonlocal view_called
            view_called = True
            return HttpResponse("ok")

        result = view("fake_request")

        assert result.status_code == 403
        assert result.content == b"Custom error."
        assert not view_called
