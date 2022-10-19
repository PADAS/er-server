import json
from unittest.mock import MagicMock, patch

import pytest
from google.cloud.pubsub_v1.subscriber.message import Message

from das_server.pubsub_gcloud_listener import (
    get_tenant_data_with_retry,
    handle_tenant_update,
    logger,
)


@pytest.fixture
def mock_message(tenant_response):
    message = MagicMock(spec=Message)
    message.data = json.dumps({"id": tenant_response["id"]}).encode("utf-8")
    return message


@patch("core.tms.HTTPClient.get_tenant_data")
def test_handle_tenant_update(mocked_tenant_client, mock_message, tenant_response, caplog):
    mocked_tenant_client.return_value = tenant_response

    logger.setLevel("INFO")
    caplog.at_level("INFO")
    handle_tenant_update(mock_message)

    assert "Updated tenant: zoo.com in cache" in caplog.text


@patch("core.tms.HTTPClient.get_tenant_data")
def test_get_tenant_data_with_retry_success(mocked_get_tenant_data, tenant_response):
    mocked_get_tenant_data.return_value = tenant_response

    result = get_tenant_data_with_retry(tenant_response["id"])

    assert result == tenant_response


@patch("das_server.pubsub_gcloud_listener.tms_api_client.get_tenant_data")
def test_get_tenant_data_with_retry_failure(mocked_get_tenant_data, tenant_response):
    mocked_get_tenant_data.side_effect = Exception()

    with pytest.raises(Exception):
        get_tenant_data_with_retry(tenant_id="c0973be2-8e11-4cb8-8463-897fb96391d0", delay=1)

    assert mocked_get_tenant_data.call_count == 3
