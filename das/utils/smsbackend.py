from django.conf import settings
from sendsms.backends.base import BaseSmsBackend
from twilio.rest import TwilioRestClient


TWILIO_ACCOUNT_SID = getattr(settings, 'SENDSMS_TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = getattr(settings, 'SENDSMS_TWILIO_AUTH_TOKEN', '')

class TwilioSmsBackend(BaseSmsBackend):
    def send_messages(self, messages):
        # This is an example backend that uses Twilio to send SMS messages
        # We don't have a Twilio account, so I'm leaving it commented out
        # If you want to use Twilio (maybe for testing something)
        # 1. Create a free trial Twilio account
        # 2. Add the following lines to local_settings
        #    SENDSMS_BACKEND='utils.smsbackend.TwilioSmsBackend'
        #    SENDSMS_TWILIO_ACCOUNT_SID=[YOUR TRIAL ACCOUNT INFO]
        #    SENDSMS_TWILIO_AUTH_TOKEN=[YOUR TRIAL ACCOUNT INFO]
        # 3. Uncomment the code below
        #
        pass

        # client = TwilioRestClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        # for message in messages:
        #     for to in message.to:
        #         try:
        #             client.sms.messages.create(
        #                 to=to,
        #                 from_=message.from_phone,
        #                 body=message.body
        #             )
        #         except:
        #             if not self.fail_silently:
        #                 raise
