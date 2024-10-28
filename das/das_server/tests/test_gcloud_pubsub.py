from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound
from google.cloud.pubsub_v1 import SubscriberClient
from google.cloud.pubsub_v1.subscriber.futures import StreamingPullFuture
from google.pubsub_v1 import Subscription
from google.pubsub_v1.types import GetSubscriptionRequest

from das_server.pubsub_gcloud_listener import GCloudPubSubListener


class TestGCloudPubSubListener:
    @pytest.fixture
    def gcloud_pubsub_listener(self):
        subscriber = MagicMock(spec=SubscriberClient)
        project_id = "test-project"
        topic_id = "test-topic"
        subscription_id = "test-subscription"

        return GCloudPubSubListener(subscriber, project_id, topic_id, subscription_id)

    def test_get_topic_path(self, gcloud_pubsub_listener):
        expected_topic_path = "projects/test-project/topics/test-topic"

        gcloud_pubsub_listener.subscriber.topic_path.return_value = expected_topic_path
        topic_path = gcloud_pubsub_listener.get_topic_path()

        assert topic_path == expected_topic_path

    def test_get_subscription_path(self, gcloud_pubsub_listener):
        expected_subscription_path = "projects/test-project/subscriptions/test-subscription"

        gcloud_pubsub_listener.subscriber.subscription_path.return_value = expected_subscription_path
        subscription_path = gcloud_pubsub_listener.get_subscription_path()

        assert subscription_path == expected_subscription_path

    @patch("das_server.pubsub_gcloud_listener.GetSubscriptionRequest")
    def test_subscription_exists(self, mock_get_subscription_request, gcloud_pubsub_listener):
        mock_get_subscription_request.return_value = GetSubscriptionRequest(subscription="test-subscription-path")

        gcloud_pubsub_listener.subscriber.get_subscription.return_value = True

        assert gcloud_pubsub_listener.subscription_exists() is True

    @patch("das_server.pubsub_gcloud_listener.GetSubscriptionRequest")
    def test_subscription_not_exists(self, mock_get_subscription_request, gcloud_pubsub_listener):
        mock_get_subscription_request.return_value = GetSubscriptionRequest(subscription="test-subscription-path")

        gcloud_pubsub_listener.subscriber.get_subscription.side_effect = NotFound("Subscription not found")

        assert gcloud_pubsub_listener.subscription_exists() is False

    def test_delete_subscription(self, gcloud_pubsub_listener):
        gcloud_pubsub_listener.delete_subscription()
        assert gcloud_pubsub_listener.subscriber.delete_subscription.call_count == 1
        assert gcloud_pubsub_listener.subscriber.delete_subscription.call_args[1] == {
            "subscription": gcloud_pubsub_listener.get_subscription_path()
        }

    def test__create_subscription(self, gcloud_pubsub_listener):
        gcloud_pubsub_listener.subscription_exists = MagicMock(return_value=True)
        gcloud_pubsub_listener.delete_subscription = MagicMock()
        gcloud_pubsub_listener.subscriber.create_subscription = MagicMock(
            return_value=Subscription(name="test-subscription")
        )

        subscription = gcloud_pubsub_listener._create_subscription()

        assert isinstance(subscription, Subscription)
        assert subscription.name == "test-subscription"

    def test_get_subscription_listener(self, gcloud_pubsub_listener):
        callback = MagicMock()
        gcloud_pubsub_listener.subscriber.subscribe = MagicMock(return_value=StreamingPullFuture(MagicMock()))
        gcloud_pubsub_listener._create_subscription = MagicMock()

        result = gcloud_pubsub_listener.get_subscription_listener(callback)

        assert isinstance(result, StreamingPullFuture)
