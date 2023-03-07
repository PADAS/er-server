import json
import logging
import time
from json import JSONDecodeError
from typing import Callable, Union

from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPICallError,
    GoogleAPIError,
    InternalServerError,
    ResourceExhausted,
    Unknown,
)
from google.api_core.retry import Retry, if_exception_type
from google.cloud.exceptions import NotFound
from google.cloud.pubsub_v1 import SubscriberClient
from google.cloud.pubsub_v1.subscriber.futures import StreamingPullFuture
from google.cloud.pubsub_v1.subscriber.message import Message
from google.pubsub_v1 import Subscription
from google.pubsub_v1.types import GetSubscriptionRequest

from django.conf import settings

from core import tms_api_client
from utils.tenant.providers import update_tenant_in_cache

logger = logging.getLogger(__name__)


TOPIC_ID = "tms-refresh-single-cache"
SUBSCRIPTION_ID = f"das-tenant-listener-{settings.CLUSTER_NAME}-{settings.CLUSTER_NAMESPACE}"


def setup_gcloud_pubsub_listener(delay: int = 3, timeout=120) -> None:
    while True:
        try:
            logger.info("Starting Gcloud pubsub TMS listener")
            streaming_pull_future = None
            with SubscriberClient() as subscriber:
                gc_listener = GCloudPubSubListener(
                    subscriber=subscriber,
                    project_id=settings.PUBSUB_PROJECT_ID,
                    topic_id=TOPIC_ID,
                    subscription_id=SUBSCRIPTION_ID,
                )
                streaming_pull_future = gc_listener.get_subscription_listener(callback=handle_tenant_update)
                streaming_pull_future.result()
        except GoogleAPIError as error:
            logger.error("An error occurred initializing GCloud pubsub listener: %s", str(error))
            if streaming_pull_future:
                streaming_pull_future.cancel()
            time.sleep(delay)


def get_tenant_data_with_retry(tenant_id: str, max_retries: int = 3, delay: int = 4) -> dict:
    for attempt in range(max_retries):
        try:
            tenant = tms_api_client.get_tenant_data(lookup=tenant_id)
            return tenant
        except Exception as error:
            logger.error("Attempt %d: Failed to get tenant data: %s", attempt + 1, str(error))
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                logger.error("Failed to get tenant data after %d attempts", max_retries)
                raise


def handle_tenant_update(message: Message, *args, **kwargs) -> None:
    try:
        data = message.data.decode("utf-8")
        data = json.loads(data)
        tenant_id = data["id"]
    except JSONDecodeError as error:
        logger.error("Failed to decode JSON data: %s", str(error))
        raise

    tenant = get_tenant_data_with_retry(tenant_id=tenant_id)

    update_tenant_in_cache(tenant_data=tenant)
    logger.info("Updated tenant: %s in cache", tenant["domain"])
    message.ack()


class GCloudPubSubListener:
    def __init__(self, subscriber: SubscriberClient, project_id: str, topic_id: str, subscription_id: str):
        self.subscriber = subscriber
        self.project_id = project_id
        self.topic_id = topic_id
        self.subscription_id = subscription_id

    def get_topic_path(self) -> str:
        return self.subscriber.topic_path(project=self.project_id, topic=self.topic_id)

    def get_subscription_path(self) -> str:
        return self.subscriber.subscription_path(project=self.project_id, subscription=self.subscription_id)

    def _get_subscription(self) -> Union[Subscription, bool]:
        try:
            subscription_path = self.get_subscription_path()
            request = GetSubscriptionRequest(subscription=subscription_path)
            subscription = self.subscriber.get_subscription(request=request)
            return subscription
        except NotFound:
            return False

    def _create_subscription(self) -> Subscription:
        predicate = if_exception_type(
            DeadlineExceeded,
            GoogleAPICallError,
            InternalServerError,
            ResourceExhausted,
            Unknown,
        )
        retry = Retry(predicate=predicate, initial=0.1, maximum=60.0, multiplier=2.0, deadline=300.0)

        return self.subscriber.create_subscription(
            name=self.get_subscription_path(),
            topic=self.get_topic_path(),
            retry=retry,
        )

    def get_or_create_subscription(self) -> Subscription:
        subscription_path = self.get_subscription_path()
        subscription = self._get_subscription()

        if subscription:
            logger.debug("Found existing subscription: %s", subscription_path)
            return subscription

        logger.debug("Creating subscription: %s", subscription_path)
        return self._create_subscription()

    def get_subscription_listener(self, callback: Callable[..., None]) -> StreamingPullFuture:
        self.get_or_create_subscription()
        return self.subscriber.subscribe(self.get_subscription_path(), callback=callback)
