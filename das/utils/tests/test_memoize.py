from unittest.mock import MagicMock

import pytest

from utils.memoize import memoize
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException


@pytest.mark.django_db
class TestMemoizeDecorator:
    @pytest.mark.usefixtures("tenant_settings")
    def test_memoize(self):
        mock = MagicMock(return_value=1)

        @memoize
        def function(argument):
            return mock(argument)

        function(3)
        function(3)
        result = function(3)

        mock.assert_called_once_with(3)
        assert result == 1

    @pytest.mark.usefixtures("tenant_settings")
    def test_memoize_per_tenant(self, monkeypatch, five_tenants):
        first_tenant_settings = MagicMock(return_value=five_tenants[0])
        second_tenant_settings = MagicMock(return_value=five_tenants[1])
        mock = MagicMock()

        @memoize
        def do_something(argument):
            mock(argument)
            return argument

        monkeypatch.setattr("utils.memoize.get_tenant_settings", first_tenant_settings)
        do_something("foo")
        do_something("foo")
        do_something("bar")
        do_something("bar")

        monkeypatch.setattr("utils.memoize.get_tenant_settings", second_tenant_settings)
        do_something("foo")
        do_something("foo")
        do_something("bar")
        do_something("bar")

        assert [("foo",), ("bar",), ("foo",), ("bar",)] == [call.args for call in mock.call_args_list]

    def test_memoize_fails_when_tenant_is_not_set_in_thread(self, monkeypatch, five_tenants):
        tenant_settings = MagicMock(side_effect=TenantNotFoundInLocalThreadException)
        mock = MagicMock()
        monkeypatch.setattr("utils.memoize.get_tenant_settings", tenant_settings)

        @memoize
        def do_something(argument):
            mock(argument)
            return argument

        with pytest.raises(TenantNotFoundInLocalThreadException):
            do_something("foo")

        assert not mock.called
