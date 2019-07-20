import functools
import json
import logging
from datetime import datetime, timedelta

import geojson
import pytz
import requests
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

DEFAULT_REQUESTS_TIMEOUT_SECS = (2, 5)
SERVICE_ERROR_CODE = 500

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


def create_subscription(gfw_info):
    geostore_id = _get_geostore_id(gfw_info)
    subscribe_json = _make_subscribe_msg(gfw_info['name'],
                                         gfw_info['alert_types'],
                                         geostore_id)
    logger.info(f'SUBS JSON {subscribe_json}')

    try:
        rsp = requests.post(url=subscriptions_endpoint,
                            headers={'Authorization': f'Bearer {gfw_info["gfw_auth_token"]}'},
                            json=subscribe_json,
                            timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
    except Exception as ex:
        logger.exception(f'Exception {ex} raised in create_subscription')
        return _make_service_response(SERVICE_ERROR_CODE,
                                      f'Error communicating with Global Forest Watch service. '
                                      f'{getattr(ex, "message", "")}')
    else:
        if rsp and rsp.status_code == status.HTTP_200_OK:
            sub_id = json.loads(rsp.text)['data']['id']
            logger.info(f'create subscription successful. {rsp.text}')
            return _make_service_response(rsp.status_code,
                                          'Success',
                                          dict(subscription_id=sub_id,
                                               geostore_id=geostore_id))
        else:
            logger.error(f'create_subscription failed with code {rsp}')
            return _make_service_response(rsp.status_code, rsp.text)


def fetch_subscription_json(gfw_info):
    try:
        rsp = requests.get(url=f'{subscriptions_endpoint}/{gfw_info.subscription_id}',
                           headers={'Authorization': f'Bearer {gfw_info["gfw_auth_token"]}'},
                           timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)

    except Exception as ex:
        logger.exception(f'Exception {ex} raised in fetch_subscription')
        return _make_service_response(SERVICE_ERROR_CODE,
                                      f'Error communicating with Global Forest Watch service. '
                                      f'{getattr(ex, "message", "")}')
    else:
        if rsp and rsp.status_code == status.HTTP_200_OK:
            logger.info(f'fetch subscription successful. {rsp.text}')
            _make_service_response(rsp.status_code,
                                   'Success',
                                   dict(json=json.loads(rsp.text)['data']))
        else:
            logger.error(f'fetch_subscription failed with code {rsp}')
            return _make_service_response(rsp.status_code, rsp.text)


def update_subscription(gfw_info, geometry_changed):
    geostore_id = gfw_info.get('geostore_id')
    if not geostore_id or geometry_changed:
        logger.info(f'GEOMETRY CHANGED. updating geostore {geometry_changed}')
        geostore_id = _get_geostore_id(gfw_info)

    subscribe_json = _make_subscribe_msg(gfw_info['name'],
                                         gfw_info['alert_types'],
                                         geostore_id)

    if not gfw_info['subscription_id']:
        # this will happen if create_subscription failed for some reason
        method = 'POST'
        url = subscriptions_endpoint
    else:
        method = 'PATCH'
        url = f'{subscriptions_endpoint}/{gfw_info["subscription_id"]}'

    try:
        rsp = requests.request(method=method,
                               url=url,
                               headers={'Authorization': f'Bearer {gfw_info["gfw_auth_token"]}'},
                               json=subscribe_json,
                               timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
    except Exception as ex:
        logger.exception(f'Exception {ex} raised in update_subscription')
        return _make_service_response(SERVICE_ERROR_CODE,
                                      f'Error communicating with Global Forest Watch service. '
                                      f'{getattr(ex, "message", "")}')
    else:
        if rsp and rsp.status_code == status.HTTP_200_OK:
            logger.info(f'update subscription successful. {rsp.text}')
            sub_id = json.loads(rsp.text)['data']['id']
            return _make_service_response(rsp.status_code,
                                          'Success',
                                          dict(subscription_id=sub_id,
                                               geostore_id=geostore_id))
        else:
            logger.error(f'update_subscription failed with code {rsp}')
            return _make_service_response(rsp.status_code, rsp.text)


def delete_subscription(model):
    try:
        rsp = requests.get(
            url=f'{subscriptions_endpoint}/{model.subscription_id}/unsubscribe',
            headers={'Authorization': f'Bearer {model["gfw_auth_token"]}'},
            timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
    except Exception as ex:
        logger.exception(f'Exception {ex} raised in delete_subscription')
        return _make_service_response(SERVICE_ERROR_CODE,
                                      f'Error communicating with Global Forest Watch service. '
                                      f'{getattr(ex, "message", "")}')
    else:
        if rsp and rsp.status_code == status.HTTP_200_OK:
            logger.info(f'delete subscription successful. {rsp.text}')
            return _make_service_response(rsp.status_code, 'Success')
        else:
            logger.error(f'delete_subscription failed with code {rsp}')
            return _make_service_response(rsp.status_code, rsp.text)


def _get_geostore_id(gfw_info):
    json_dict = dict(geojson=geojson.loads(gfw_info['subscription_geometry'].geojson))

    try:
        rsp = requests.post(
            url=f'{settings.GFW_API_ROOT}/geostore',
            json=json_dict,
            timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
    except Exception as ex:
        logger.exception(f'Exception {ex} raised in get_geostore_id')
        return _make_service_response(SERVICE_ERROR_CODE,
                                      f'Error communicating with Global Forest Watch service. '
                                      f'{getattr(ex, "message", "")}')
    else:
        if rsp and rsp.status_code == status.HTTP_200_OK:
            geostore_rsp = json.loads(rsp.text)
            return geostore_rsp['data']['id']
        else:
            logger.error(f'_update_geostore failed with code {rsp}')
            return _make_service_response(rsp.status_code, rsp.text)


def _make_subscribe_msg(name, alert_types, geostore_id):

    subscription = {
        'name': name,
        'application': 'gfw',
        'language': 'en',
        'datasets': alert_types,
        'resource': {
            'type': 'URL',
            'content': f'{get_webhook_base_url()}/?auth={get_gfw_access_token(get_gfw_user())}'
        },
        'params': {'geostore': geostore_id}
    }

    return subscription


def _make_service_response(status_code, status_text, data=None):
    return {'status_code': status_code,
            'text': status_text,
            'data': data}


def exception_wrapper(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            response = func(*args, **kwargs)
        except Exception as ex:
            logger.error(f'Exception {ex} raised in {func}')
            response = _make_service_response(SERVICE_ERROR_CODE,
                                              f'Error communicating with Global Forest Watch service {func} raised {ex}')

        return response

    return wrapper
