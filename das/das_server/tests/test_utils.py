import json
import logging

import pytest

from das_server.utils import append_domain_into_message


class TestAppendDomainToMessage:
    def test_append_domain_to_message_when_message_is_dict(self):
        message = {"message": "new message"}
        domain = "domain.com"
        result = append_domain_into_message(message=message, domain=domain)

        assert isinstance(result, dict)
        assert result["domain"] == domain

    def test_append_domain_to_message_when_message_is_json_string(self):
        message = json.dumps({"message": "new message"})
        domain = "domain.com"
        result = append_domain_into_message(message=message, domain=domain)

        assert isinstance(result, str)
        assert "domain" in result
        assert domain in result

    def test_append_domain_to_message_with_message_not_dict_nor_string(self, caplog):
        caplog.set_level(logging.INFO)

        with pytest.raises(Exception, match="message should be dict or str") as exc_info:
            append_domain_into_message(message=None, domain="domain1.com")
