import logging
from django.conf import settings
from sendsms.backends.base import BaseSmsBackend
from twilio.rest import TwilioRestClient
import requests

logger = logging.getLogger(__name__)


class TwilioSmsBackend(BaseSmsBackend):
    TWILIO_ACCOUNT_SID = getattr(settings, 'SENDSMS_TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = getattr(settings, 'SENDSMS_TWILIO_AUTH_TOKEN', '')

    def send_messages(self, messages):
        # This is an example backend that uses Twilio to send SMS messages
        # We don't have a Twilio account, so I'm leaving it commented out
        # If you want to use Twilio (maybe for testing something)
        # 1. Create a free trial Twilio account
        # 2. Add or update the following lines in settings
        #    SENDSMS_BACKEND='utils.smsbackend.TwilioSmsBackend'
        #    SENDSMS_TWILIO_ACCOUNT_SID=[YOUR TRIAL ACCOUNT INFO]
        #    SENDSMS_TWILIO_AUTH_TOKEN=[YOUR TRIAL ACCOUNT INFO]

        logger.info("Send message via Twilio")

        client = TwilioRestClient(self.TWILIO_ACCOUNT_SID,
                                  self.TWILIO_AUTH_TOKEN)
        for message in messages:
            for to in message.to:
                try:
                    client.sms.messages.create(
                        to=to,
                        from_=message.from_phone,
                        body=message.body
                    )
                except:
                    if not self.fail_silently:
                        raise


class AfricasTalkingBackend(BaseSmsBackend):
    username = getattr(settings, 'SENDSMS_AFRICAS_TALKING_USERNAME', '')
    apikey = getattr(settings, 'SENDSMS_AFRICAS_TALKING_API_KEY', '')
    sms_url = 'https://api.africastalking.com/restless/send'

    def send_messages(self, messages):
        if self.username is None or self.username == '' or self.apikey is None or self.apikey == '':
            return
        for message in messages:
            for to in message.to:
                try:
                    parameters = {'username': self.username,
                                  'Apikey': self.apikey,
                                  'to': str(to),
                                  'message': str(message.body)}

                    response = requests.get(self.sms_url, params=parameters)
                    if not response.ok:
                        err_msg = 'Error sending an sms to {0): {1}'.format(
                            to, response)
                        logger.error(err_msg)

                except Exception as ex:
                    err_msg = 'Error sending an sms to {0): {1}'.format(
                        to, response)
                    logger.error(err_msg, ex)
