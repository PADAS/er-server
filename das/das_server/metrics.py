import logging
import simplejson as json
import django.contrib.auth.signals
from django.dispatch import receiver

logger = logging.getLogger(__name__)



@receiver(django.contrib.auth.signals.user_login_failed)
def user_login_failed(sender, credentials, **kwargs):
    message = dict(id='user_login_failure', username=credentials['username'])
    logger.info(json.dumps(message))


@receiver(django.contrib.auth.signals.user_logged_in)
def user_logged_in(sender, user, request, **kwargs):
    message = dict(id='user_login', username=user.username, user_id = user.id,
                   remote_addr=request.META['REMOTE_ADDR'],
                   user_agent=request.META['HTTP_USER_AGENT'])
    logger.info(json.dumps(message))


@receiver(django.contrib.auth.signals.user_logged_out)
def user_logged_out(sender, user, request, **kwargs):
    message = dict(id='user_logout', username=user.username, user_id = user.id,
                   remote_addr=request.META['REMOTE_ADDR'])
    logger.info(json.dumps(message))
