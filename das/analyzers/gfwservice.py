import json
import logging
from datetime import datetime, timedelta

import pytz
import requests
import geojson
from django.conf import settings
from django.urls import reverse
from oauth2_provider.models import Application, generate_client_secret
from oauthlib.common import generate_token
from rest_framework import status

from accounts.models import User
from sensors.gfw_alert_handler import GFWAlertHandler

DEFAULT_GFW_PROVIDER_KEY = 'gfw'
GFW_OAUTH_APPLICATION_ID = 'gfw-application'

from oauth2_provider.models import AccessToken

DEFAULT_REQUESTS_TIMEOUT_SECS = 5

logger = logging.getLogger(__name__)
subscriptions_endpoint = f'{settings.GFW_API_ROOT}/subscriptions'
geostore_endpoint = f'{settings.GFW_API_ROOT}/geostore'


def get_webhook_base_url(provider_key=GFWAlertHandler.PROVIDER_KEY):
    '''
    Create a base URL for a webhook callback.
    :param provider_key:
    :return:
    '''
    path = reverse('sensor-observation-view',
                   kwargs={'sensor_type': GFWAlertHandler.SENSOR_TYPE,
                           'provider_key': provider_key})

    return ''.join([getattr(settings, 'UI_SITE_URL'), path])


def get_gfw_user():
    '''
    Get the system-generated user to associate with the Global Forest Watch events.
    :return:
    '''
    user, create = User.objects.get_or_create(username='gfwwebhookuser',
                                              defaults={'first_name': 'GFW Webhook',
                                                        'last_name': 'GFW Webhook',
                                                        'password': User.objects.make_random_password()
                                                        })
    return user


def get_gfw_oauth2_application():
    app, created = Application.objects.get_or_create(client_id=GFW_OAUTH_APPLICATION_ID,
                                                     defaults={
                                                         'client_type': Application.CLIENT_CONFIDENTIAL,
                                                         'authorization_grant_type': Application.GRANT_CLIENT_CREDENTIALS,
                                                         'client_secret': generate_client_secret(),
                                                         'name': 'Global Forest Watch Client App',
                                                         'skip_authorization': True,
                                                     })
    return app


def get_gfw_access_token(user, ttl_days=5*365):
    '''
    Get a long-lived token to be used for global forest watch callbacks.
    '''

    try:
        app = get_gfw_oauth2_application()

    except Exception:
        logger.error(
            'There exists no Oauth2 Application with client_id %s', GFW_OAUTH_APPLICATION_ID)
    else:
        try:
            access_token = AccessToken.objects.filter(user=user,
                                                      application=app,
                                                      scope='write',
                                                      expires__gt=datetime.now(tz=pytz.utc)+timedelta(days=365)).latest('expires')
        except AccessToken.DoesNotExist:
            logger.info('Valid access token not found, will create new token')
            access_token = AccessToken.objects.create(
                user=user, application=app, scope='write',
                expires=datetime.now(tz=pytz.utc) + timedelta(days=ttl_days), token=generate_token())

        return access_token


def create_subscription(model_instance):
    _update_geostore(model_instance)
    subscribe_json = _build_subscribe_msg(model_instance)
    gfw_auth_token = model_instance.additional['gfw_auth_token']
    logger.info(f'SUBS JSON {subscribe_json}')
    rsp = requests.post(url=subscriptions_endpoint,
                        headers={'Authorization': f'Bearer {gfw_auth_token}'},
                        json=subscribe_json,
                        timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)

    logger.info(f'subscription response: {rsp} \n {rsp.text}')

    if rsp.status_code == status.HTTP_200_OK:
        model_instance.subscription_id = json.loads(rsp.text)['data']['id']
        logger.info(f'subscription successful. id: {model_instance.subscription_id}')
    else:
        logger.error(f'create_subscription failed with code {rsp.status_code} msg: {rsp.text}')


def fetch_subscription(model_instance):
    gfw_auth_token = model_instance.additional['gfw_auth_token']
    rsp = requests.get(url=f'{subscriptions_endpoint}/{model_instance.subscription_id}',
                       headers={'Authorization': f'Bearer {gfw_auth_token}'},
                       timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
    if rsp.status_code != status.HTTP_200_OK:
        logger.error(f'fetch_subscription failed with code {rsp.status_code} msg: {rsp.text}')


def update_subscription(model_instance):
    if not model_instance.subscription_geometry_pre_save.equals_exact(model_instance.subscription_geometry, 1.0):
        logger.info(f'GEOMETRY CHANGED. updating geostore')
        _update_geostore(model_instance)
    else:
        logger.info(f'GEOMETRY NOT CHANGED')

    subscribe_json = _build_subscribe_msg(model_instance)
    gfw_auth_token = model_instance.additional['gfw_auth_token']
    rsp = requests.patch(url=f'{subscriptions_endpoint}/{model_instance.subscription_id}',
                         headers={'Authorization': f'Bearer {gfw_auth_token}'},
                         json=subscribe_json,
                         timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)

    if rsp.status_code == status.HTTP_200_OK:
        logger.info(f'update subscription successful. {rsp.text}')
    else:
        logger.error(f'update_subscription failed with code {rsp.status_code} msg: {rsp.text}')


def delete_subscription(model_instance):
    gfw_auth_token = model_instance.additional['gfw_auth_token']
    rsp = requests.get(url=f'{subscriptions_endpoint}/{model_instance.subscription_id}/unsubscribe',
                       headers={'Authorization': f'Bearer {gfw_auth_token}'},
                       timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)

    if rsp.status_code == status.HTTP_200_OK:
        logger.info(f'delete subscription successful. {rsp.text}')
    else:
        logger.error(f'delete_subscription failed with code {rsp.status_code} msg: {rsp.text}')


def _update_geostore(model_instance):
    json_dict = dict(geojson=geojson.loads(model_instance.subscription_geometry.geojson))
    rsp = requests.post(url=f'{settings.GFW_API_ROOT}/geostore',
                        json=json_dict,
                        timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
    if rsp.status_code == status.HTTP_200_OK:
        geostore_rsp = json.loads(rsp.text)
        model_instance.geostore_id = geostore_rsp['data']['id']
    else:
        logger.error(f'_update_geostore failed with code {rsp.status_code} msg: {rsp.text}')


def _build_subscribe_msg(model):

    subscription = {
        'name': model.name,
        'application': 'gfw',
        'language': 'en',
        'datasets': model.additional['alert_types'],
        'resource': {
            'type': 'URL',
            'content': f'{get_webhook_base_url()}/?auth={get_gfw_access_token(get_gfw_user())}'
        },
        'params': {'geostore': model.geostore_id}
    }

    return subscription

