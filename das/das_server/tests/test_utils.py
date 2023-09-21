import json
import logging

import pytest

from das_server.utils import (
    append_domain_to_message,
    wrap_message_processing_with_tenant_context,
)
from utils.tenant.thread import get_tenant_settings


class TestAppendDomainToMessage:
    def test_append_domain_to_message_when_message_is_dict(self):
        message = {"message": "new message"}
        domain = "domain.com"
        result = append_domain_to_message(message=message, domain=domain)

        assert isinstance(result, dict)
        assert result["domain"] == domain

    def test_append_domain_to_message_when_message_is_json_string(self):
        message = json.dumps({"message": "new message"})
        domain = "domain.com"
        result = append_domain_to_message(message=message, domain=domain)

        assert isinstance(result, str)
        assert "domain" in result
        assert domain in result

    def test_append_domain_to_message_with_message_not_dict_nor_string(self, caplog):
        caplog.set_level(logging.INFO)

        with pytest.raises(Exception, match="message should be dict or str") as exc_info:
            append_domain_to_message(message=None, domain="domain1.com")


class TestTenantContextFromMessage:
    def test_pubsub_message_contains_tenant(self, tenant_settings, memory_store_client_mock):
        def tenant_callback(*args, **kwargs):
            assert get_tenant_settings() is not None

        tenant = get_tenant_settings()
        wrapped = wrap_message_processing_with_tenant_context(tenant_callback)
        message = {"domain": tenant.domain}
        wrapped(message)

    def test_pubsub_message_does_not_contain_tenant(self, tenant_settings, feature_tms, caplog):
        def tenant_callback(*args, **kwargs):
            assert "Tenant Domain not found in PubSub message" not in caplog.text
            assert False, "Tenant not found message changed, this test needs updating"

        caplog.set_level(logging.WARNING)
        wrapped = wrap_message_processing_with_tenant_context(tenant_callback)
        message = {}
        wrapped(message)
