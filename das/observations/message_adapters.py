import json
import logging
import math
from datetime import datetime

import requests
from django.conf import settings

from accounts.models import User
from observations.models import ERRORED, SENT
from observations.models import Source, Message

logger = logging.getLogger(__name__)


class BaseMessageAdapter:

    def __init__(self, payload={}, device_key=None):
        self.payload = payload
        self.device_key = device_key

    @staticmethod
    def send_msg_to_device(payload):
        raise NotImplemented('An extending class must implement send_msg_to_device.')

    @staticmethod
    def update_message_status(message_id, status):
        Message.objects.filter(id=message_id).update(status=status)


class InReachAdapter(BaseMessageAdapter):
    endpoint = settings.INREACH_INBOUND_ENDPOINT
    username = settings.INREACH_USERNAME
    password = settings.INREACH_PASSWORD

    @staticmethod
    def send_msg_to_device(data, source, user_email):
        timestamp = math.trunc(datetime.timestamp(datetime.now()) * 1000)
        device_id = source.manufacturer_id
        payload = {
            "Messages": [{
                "Message": data.get('text'),
                "Recipients": [device_id],
                "Sender": user_email or settings.FROM_EMAIL,
                "Timestamp": f"/Date({timestamp})/"
            }]
        }

        try:
            headers = {'content-type': 'application/json', 'accept': 'application/json'}
            res = requests.post(
                url=InReachAdapter.endpoint, auth=(InReachAdapter.username, InReachAdapter.password),
                json=payload, headers=headers)
            if res.status_code != 200:
                status = ERRORED
                error_message = json.loads(res.text).get('Message')
                logger.exception(f'Error sending message to device: {device_id} - {error_message}')
            else:
                status = SENT
        except Exception as ex:
            logger.exception(f'Exception {ex} raised when sending message to device: {device_id}')
            status = ERRORED
        InReachAdapter.update_message_status(data.get('id'), status)


DEVICE_ADAPTER_MAPPING = {
    'inreach-provider': InReachAdapter
}


def _handle_outbox_message(payload, user_email):
    device_id = payload.get('device')
    if device_id:
        try:
            source = Source.objects.get(id=device_id)
        except Source.objects.DoesNotExist:
            logger.exception(f'Device: {device_id} does not exist')
        else:
            adapter = DEVICE_ADAPTER_MAPPING.get(source.provider.provider_key, InReachAdapter)
            if source.provider.messaging_enabled:
                adapter.send_msg_to_device(payload, source, user_email)
            else:
                logger.error(f'Messaging not enabled for this device: {device_id}')
