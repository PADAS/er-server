import logging

from django.conf import settings
from twilio.rest import Client

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
TWILIO_FROM_NUMBER = getattr(settings, 'WHATSAPP_FROM_NUMBER', '')


def send_whatsapp(body, to, fail_silently=True):
    logger.info("Send message via Twilio")
    if not TWILIO_FROM_NUMBER:
        raise ValueError("WHATSAPP_FROM_NUMBER not configured in settings.py")
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    from_number = '+' + TWILIO_FROM_NUMBER if not TWILIO_FROM_NUMBER.startswith('+') else TWILIO_FROM_NUMBER
    try:
        client.messages.create(body=body, from_=f"whatsapp:{from_number}", to=f"whatsapp:{to}")
    except Exception as e:
        logger.error("Error sending whatsapp message {0}".format(str(e)))
        if not fail_silently:
            raise

