import functools
import json
import logging
from datetime import datetime, timedelta, date

import geojson
import pytz
import requests
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from oauth2_provider.models import AccessToken
from oauth2_provider.models import Application, generate_client_secret
from oauthlib.common import generate_token
from rest_framework import status

from analyzers.gfw_utils import get_gfw_user, make_download_url
from sensors.handlers import GFWAlertHandler

DEFAULT_REQUESTS_TIMEOUT_SECS = (2, 5)
SERVICE_ERROR_CODE = -1
DEFAULT_GFW_PROVIDER_KEY = 'gfw'
GFW_OAUTH_APPLICATION_ID = 'gfw-application'
NETWORK_ERROR_MESSAGE = _('Network error occurred while setting up your subscription. Please try again later. For further assistance contact Support.')
GFW_ERROR_MESSAGE = _('While setting up your subscription, GFW responded with the following error. For further assistance contact Support. GFW error:')

logger = logging.getLogger(__name__)
subscriptions_endpoint = f'{settings.GFW_API_ROOT}/subscriptions'
geostore_endpoint = f'{settings.GFW_API_ROOT}/geostore'
login_endpoint = 'https://production-api.globalforestwatch.org/auth/login'


def get_webhook_base_url(provider_key=GFWAlertHandler.PROVIDER_KEY):
    '''
    Create a base URL for a webhook callback.
    :param provider_key:
    :return:
    '''
    path = reverse('gfahandler-view',
                   kwargs={'provider_key': provider_key})

    return ''.join([getattr(settings, 'UI_SITE_URL'), path])


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


def get_gfw_auth_token():
    token = None
    gfw_credentials = getattr(settings, 'GFW_CREDENTIALS', None)
    if gfw_credentials:
        try:
            login_response = requests.post(url=login_endpoint,
                                           json={'email': gfw_credentials.get('username'),
                                                 'password': gfw_credentials.get('password')})
        except Exception as ex:
            logger.exception('Exception %s raised when logging in', ex)
            token = None
        else:
            if login_response and login_response.status_code == status.HTTP_200_OK:
                token = json.loads(login_response.text).get('data', {}).get('token')

    return token


def create_subscription(gfw_info):
    token = get_gfw_auth_token()
    if token:
        is_valid, geostore_response = _validate_geostore(_get_geostore_id(gfw_info))
        if not is_valid:
            return geostore_response
        else:
            geostore_id = geostore_response

        subscribe_json = _make_subscribe_msg(gfw_info['name'],
                                             gfw_info['alert_types'],
                                             geostore_id)
        logger.debug('subscription JSON %s', subscribe_json)

        try:
            rsp = requests.post(url=subscriptions_endpoint,
                                headers={'Authorization': f'Bearer {token}'},
                                json=subscribe_json,
                                timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
        except Exception as ex:
            logger.exception('Exception %s raised in create_subscription', ex)
            return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)
        else:
            if rsp and rsp.status_code == status.HTTP_200_OK:
                sub_id = json.loads(rsp.text).get('data', {}).get('id')
                logger.debug('create subscription successful. %s', rsp.text)
                return _make_service_response(rsp.status_code,
                                              'Success',
                                              dict(subscription_id=sub_id,
                                                   geostore_id=geostore_id))
            else:
                logger.error('create_subscription failed with code %s', rsp)
                err_msg = f'{GFW_ERROR_MESSAGE} {_get_error_detail_as_string(rsp.text)}'
                return _make_service_response(rsp.status_code, _(err_msg))
    else:
        return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)


def fetch_subscription_json(gfw_info):
    token = get_gfw_auth_token()
    if token:
        try:
            rsp = requests.get(url=f'{subscriptions_endpoint}/{gfw_info.subscription_id}',
                               headers={'Authorization': f'Bearer {token}'},
                               timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)

        except Exception as ex:
            logger.exception('Exception %s raised in fetch_subscription', ex)
            return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)
        else:
            if rsp and rsp.status_code == status.HTTP_200_OK:
                logger.debug('fetch subscription successful. %s', rsp.text)
                _make_service_response(rsp.status_code,
                                       'Success',
                                       dict(json=json.loads(rsp.text).get('data', {})))
            else:
                logger.error('fetch_subscription failed with code %s', rsp)
                err_msg = f'{GFW_ERROR_MESSAGE} {_get_error_detail_as_string(rsp.text)}'
                return _make_service_response(rsp.status_code, _(err_msg))
    else:
        return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)


def update_subscription(gfw_info, geometry_changed):
    token = get_gfw_auth_token()
    if token:
        geostore_id = gfw_info.get('geostore_id')
        if not geostore_id or geometry_changed:
            logger.debug('geometry changed. updating geostore %s', str(geometry_changed))
            is_valid, geostore_response = _validate_geostore(_get_geostore_id(gfw_info))
            if not is_valid:
                return geostore_response
            else:
                geostore_id = geostore_response

        subscribe_json = _make_subscribe_msg(gfw_info['name'],
                                             gfw_info['alert_types'],
                                             geostore_id)

        if not gfw_info.get('subscription_id'):
            # this will happen if create_subscription failed for some reason
            method = 'POST'
            url = subscriptions_endpoint
        else:
            method = 'PATCH'
            url = f'{subscriptions_endpoint}/{gfw_info.get("subscription_id")}'

        try:
            rsp = requests.request(method=method,
                                   url=url,
                                   headers={'Authorization': f'Bearer {token}'},
                                   json=subscribe_json,
                                   timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
        except Exception as ex:
            logger.exception('Exception %s raised in update_subscription', ex)
            return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)
        else:
            if rsp and rsp.status_code == status.HTTP_200_OK:
                logger.debug('update subscription successful. %s', rsp.text)
                sub_id = json.loads(rsp.text).get('data', {}).get('id')
                return _make_service_response(rsp.status_code,
                                              'Success',
                                              dict(subscription_id=sub_id,
                                                   geostore_id=geostore_id))
            else:
                logger.error('update_subscription failed with code %s', rsp)
                err_msg = f'{GFW_ERROR_MESSAGE} {_get_error_detail_as_string(rsp.text)}'
                return _make_service_response(rsp.status_code, _(err_msg))

    else:
        return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)


def delete_subscription(model):
    token = get_gfw_auth_token()
    if token:
        try:
            rsp = requests.get(url=f'{subscriptions_endpoint}/{model.subscription_id}/unsubscribe',
                               headers={'Authorization': f'Bearer {token}'},
                               timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
        except Exception as ex:
            logger.exception('Exception %s raised in delete_subscription', ex)
            return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)
        else:
            if rsp and rsp.status_code == status.HTTP_200_OK:
                logger.debug('delete subscription successful. %s', rsp.text)
                return _make_service_response(rsp.status_code, 'Success')
            else:
                logger.error('delete_subscription failed with code %s', rsp)
                err_msg = f'{GFW_ERROR_MESSAGE} {_get_error_detail_as_string(rsp.text)}'
                return _make_service_response(rsp.status_code, _(err_msg))
    else:
        return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)


def _get_geostore_id(gfw_info):
    json_dict = dict(geojson=geojson.loads(gfw_info['subscription_geometry'].geojson))

    try:
        rsp = requests.post(url=f'{settings.GFW_API_ROOT}/geostore',
                            json=json_dict,
                            timeout=DEFAULT_REQUESTS_TIMEOUT_SECS)
    except Exception as ex:
        logger.exception('Exception %s raised in get_geostore_id', ex)
        return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)
    else:
        if rsp and rsp.status_code == status.HTTP_200_OK:
            return json.loads(rsp.text).get('data', {}).get('id')
        else:
            logger.error(f'_get_geostore_id failed. {rsp.status_code} {rsp.text} geostore geojson: {json.dumps(json_dict)}')
            err_msg = f'{GFW_ERROR_MESSAGE} {_get_error_detail_as_string(rsp.text)}'
            return _make_service_response(rsp.status_code, _(err_msg))


def _validate_geostore(geostore):
    if not geostore or type(geostore) != str:
        return False, geostore
    # else we have a valid geostore_id from gfw. lets verify that its not too big for glad alerts download
    # alerts downloaded or the date range don't matter
    today = date.today()
    download_url = make_download_url(geostore, today, today)
    try:
        response = requests.get(download_url)
    except Exception as ex:
        logger.exception(f'Exception {ex} raised in validate_geostore for geostore {geostore}')
        return _make_service_response(SERVICE_ERROR_CODE, NETWORK_ERROR_MESSAGE)
    else:
        if response.status_code == status.HTTP_200_OK:
            payload = response.json()
            if 'data' in payload:  # if the geostore is good, the data element contains alerts
                return True, geostore
            else:  # otherwise there's no data element and we get an errors element with details of errors.
                logger.warning(f'download test for geostore {geostore} returned error {payload}')
                err_msg = f'{GFW_ERROR_MESSAGE} {_get_error_detail_as_string(response.text)}'
                return False, _make_service_response(SERVICE_ERROR_CODE, _(err_msg))
        else:
            logger.error(f'validate_geostore failed with code {response} for geostore {geostore}')
            err_msg = f'{GFW_ERROR_MESSAGE} {_get_error_detail_as_string(response.text)}'
            return False, _make_service_response(response.status_code, _(err_msg))


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


def _get_error_detail_as_string(response_text):
    return ". ".join(e.get('detail') for e in json.loads(response_text).get('errors'))


def exception_wrapper(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            response = func(*args, **kwargs)
        except Exception as ex:
            response = _make_service_response(SERVICE_ERROR_CODE,
                                              f'Error communicating with Global Forest Watch service {func} raised {ex}')

        return response

    return wrapper
