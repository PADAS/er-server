import json
import logging
import math
from datetime import datetime
import pytz

import requests
from django.conf import settings

from accounts.models import User
from observations.models import ERRORED, SENT
from observations.models import Source, Message
from utils.json import parse_bool

logger = logging.getLogger(__name__)


class BaseMessageAdapter:

    def __init__(self, payload=None, device_key=None):
        self.payload = payload or {}
        self.device_key = device_key

    @classmethod
    def send_msg_to_source(cls, msg_object, message_conf, user_email=None):
        raise NotImplemented(
            'An extending class must implement send_msg_to_device.')

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

    @staticmethod
    def send_msg_to_source(message, message_config, user_email):
        timestamp = math.trunc(datetime.timestamp(datetime.now()) * 1000)
        manufacturer_id = message.device.manufacturer_id
        message_text = message.text

        payload = {
            "Messages": [{
                "Message": message_text,
                "Recipients": [manufacturer_id],
                "Sender": user_email or settings.FROM_EMAIL,
                "Timestamp": f"/Date({timestamp})/"
            }]
        }

        try:
            headers = {'content-type': 'application/json',
                       'accept': 'application/json'}
            res = requests.post(
                url=InReachAdapter.endpoint, auth=(
                    InReachAdapter.username, InReachAdapter.password),
                json=payload, headers=headers)
            if res.status_code != 200:
                status = ERRORED
                error_message = json.loads(res.text).get('Message')
                logger.exception(
                    f'Error sending message to manufacturer_id: {manufacturer_id} - {error_message}')
            else:
                status = SENT
        except Exception as ex:
            logger.exception(
                f'Exception {ex} raised when sending message to device: {manufacturer_id}')
            status = ERRORED
        InReachAdapter.update_message_status(message.id, status)


class SmartIntegrateMessageAdapter(BaseMessageAdapter):

    @classmethod
    def send_msg_to_source(cls, message, message_config, user_email):
        manufacturer_id = message.device.manufacturer_id
        message_text = message.text

        payload = {
            'device_ids': [manufacturer_id],
            'sender': user_email or settings.FROM_EMAIL,
            'created_at': message.created_at.isoformat(),
            'text': message_text
        }
        path = '?apikey='.join([message_config.get('url'), message_config.get('apikey')])
        try:
            response = requests.post(url=path, json=payload)
        except requests.exceptions.RequestException as exc:
            logger.exception(f'Request failed with exception error: {exc}')
        else:
            if response.ok:
                cls.update_message_status(message_id=message.id, status=SENT)
            else:
                cls.update_message_status(message_id=message.id, status=ERRORED)


ADAPTER_MAPPING = {
    'inreach-adapter': InReachAdapter,
    'smart-integrate-adapter': SmartIntegrateMessageAdapter,
}


def _handle_outbox_message(message_id, user_email):
    message = Message.objects.get(id=message_id)
    source = message.device

    if source:
        try:
            source = Source.objects.get(id=source.id)
        except Source.objects.DoesNotExist:
            logger.exception(f'Source with this id {source.id} does not exist')
        else:
            message_conf = source.provider.additional.get('messaging_config')
            if message_conf:
                adapter_type = message_conf.get('adapter_type')
                adapter_cls = ADAPTER_MAPPING.get(adapter_type)

                source_2way_msg_config = source.additional.get('two_way_messaging')
                provider_2way_msg_config = source.provider.additional.get('two_way_messaging', False)

                if provider_2way_msg_config and (parse_bool(source_2way_msg_config) or source_2way_msg_config in (None, "")) and adapter_cls:
                    adapter_cls.send_msg_to_source(message, message_conf, user_email)
                else:
                    logger.debug(f'Messaging not enabled for this source: {source.id}')
