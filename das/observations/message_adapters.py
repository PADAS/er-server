import logging
import math
from datetime import datetime

import requests

from django.conf import settings

from observations.models import ERRORED, SENT, Message, Source
from utils.json import parse_bool

logger = logging.getLogger(__name__)


class SendError(Exception):
    pass


class InReachAdapterSendError(SendError):
    pass


class SmartIntegrateAdapterSendError(SendError):
    pass


class BaseMessageAdapter:

    def __init__(self, payload=None, device_key=None):
        self.payload = payload or {}
        self.device_key = device_key

    @classmethod
    def send_msg_to_source(cls, msg_object, message_conf, user_email=None):
        raise NotImplemented("An extending class must implement send_msg_to_device.")

    @staticmethod
    def update_message_status(message_id, status):
        try:
            msg = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            logger.exception(f"Message with this {id} DoesNotExist.")
        else:
            msg.status = status
            msg.save()

    @classmethod
    def get_classname(cls):
        return cls.__name__


class InReachAdapter(BaseMessageAdapter):
    endpoint = settings.INREACH_INBOUND_ENDPOINT
    username = settings.INREACH_USERNAME
    password = settings.INREACH_PASSWORD

    @classmethod
    def send_msg_to_source(cls, message, message_config, user_email):
        timestamp = math.trunc(datetime.timestamp(datetime.now()) * 1000)
        manufacturer_id = message.device.manufacturer_id
        message_text = message.text

        payload = {
            "Messages": [
                {
                    "Message": message_text,
                    "Recipients": [manufacturer_id],
                    "Sender": user_email or settings.FROM_EMAIL,
                    "Timestamp": f"/Date({timestamp})/",
                }
            ]
        }
        headers = {"content-type": "application/json", "accept": "application/json"}

        try:
            response = requests.post(
                url=InReachAdapter.endpoint,
                auth=(InReachAdapter.username, InReachAdapter.password),
                json=payload,
                headers=headers,
            )
        except requests.exceptions.RequestException as exc:
            logger.exception(f"Request failed with exception error: {exc}")
            cls.update_message_status(message_id=message.id, status=ERRORED)
            # have seen requests.exceptions.SSLError, requests.exceptions.ConnectionError
            raise InReachAdapterSendError(
                f"Exception sending message to manufacturer_id: {manufacturer_id}, error: {exc}"
            )
        else:
            if response.ok:
                cls.update_message_status(message_id=message.id, status=SENT)
            else:
                cls.update_message_status(message_id=message.id, status=ERRORED)
                raise InReachAdapterSendError(
                    f"Error sending message to manufacturer_id: {manufacturer_id}, code: {response.status_code}, error: {response.text}"
                )


class SmartIntegrateMessageAdapter(BaseMessageAdapter):

    @classmethod
    def send_msg_to_source(cls, message, message_config, user_email):
        manufacturer_id = message.device.manufacturer_id
        message_text = message.text

        payload = {
            "device_ids": [manufacturer_id],
            "sender": user_email or settings.FROM_EMAIL,
            "created_at": message.created_at.isoformat(),
            "text": message_text,
        }

        qparams = {"apikey", message_config.get("apikey")}
        try:
            response = requests.post(url=message_config.get("url"), params=qparams, json=payload)
        except requests.exceptions.RequestException as exc:
            logger.exception(f"Request failed with exception error: {exc}.", extra={"message_id": message.id})
            cls.update_message_status(message_id=message.id, status=ERRORED)
            # have seen requests.exceptions.SSLError, requests.exceptions.ConnectionError
            raise SmartIntegrateAdapterSendError(
                f"Exception sending message to manufacturer_id: {manufacturer_id}, error: {exc}, message_id: {message.id}"
            )
        else:
            if response.ok:
                cls.update_message_status(message_id=message.id, status=SENT)
            else:
                cls.update_message_status(message_id=message.id, status=ERRORED)
                raise SmartIntegrateAdapterSendError(
                    f"Error sending message to manufacturer_id: {manufacturer_id}, code: {response.status_code}, error: {response.text}, message_id: {message.id}"
                )


ADAPTER_INREACH = "inreach-adapter"
ADAPTER_SMART_INTEGRATE = "smart-integrate-adapter"
ADAPTER_MAPPING = {
    ADAPTER_INREACH: InReachAdapter,
    ADAPTER_SMART_INTEGRATE: SmartIntegrateMessageAdapter,
}


def _handle_outbox_message(message_id, user_email):
    message = Message.objects.get(id=message_id)
    source = message.device

    if source:
        try:
            source = Source.objects.get(id=source.id)
        except Source.objects.DoesNotExist:
            logger.exception(f"Source with this id {source.id} does not exist", extra={"message_id": message.id})
            BaseMessageAdapter.update_message_status(message_id=message.id, status=ERRORED)
            return

        message_conf = source.provider.additional.get("messaging_config")
        if not message_conf:
            logger.warning(
                f"No messaging config found for this source: {source.id}, but we received a message {message.id} to send",
                extra={"message_id": message.id, "provider_id": source.provider.id},
            )
            BaseMessageAdapter.update_message_status(message_id=message.id, status=ERRORED)
            return

        adapter_type = message_conf.get("adapter_type")
        adapter_cls = ADAPTER_MAPPING.get(adapter_type)

        provider_2way_msg_enabled = source.provider.additional.get("two_way_messaging", False)
        source_2way_msg_config = source.additional.get("two_way_messaging", None)
        # by default, the source's two-way messaging is enabled if the provider's two-way messaging is enabled and not explicitly disabled on the source
        source_2way_msg_enabled = (
            parse_bool(source_2way_msg_config) or source_2way_msg_config in (None, "") and provider_2way_msg_enabled
        )

        if not source_2way_msg_enabled:
            logger.warning(
                f"Messaging not enabled for this source: {source.id}, but we received a message {message.id} to send"
            )
            BaseMessageAdapter.update_message_status(message_id=message.id, status=ERRORED)
            return

        if not adapter_cls:
            logger.warning(
                f"No adapter found for this source: {source.id}, but we received a message {message.id} to send"
            )
            BaseMessageAdapter.update_message_status(message_id=message.id, status=ERRORED)
            return

        if adapter_type == ADAPTER_INREACH:
            logger.warning(
                "InReach adapter is deprecated, please use SmartIntegrate adapter instead for outbox messages.",
                extra={"message_id": message.id, "provider_id": source.provider.id},
            )

        adapter_cls.send_msg_to_source(message, message_conf, user_email)
