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

logger = logging.getLogger(__name__)


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
        access_token = AccessToken.objects.filter(user=user,
                                                  application=app,
                                                  scope='write',
                                                  expires__gt=datetime.now(tz=pytz.utc)+timedelta(days=365)).latest('expires')

        if not access_token:
            access_token = AccessToken.objects.create(
                user=user, application=app, scope='write', expires__gt=datetime.now(tz=pytz.utc),
                expires=datetime.now(tz=pytz.utc) + timedelta(days=ttl_days), token=generate_token())

        return access_token


def create_subscription(model_instance):
    spatial_features = model_instance.spatial_feature_group.features.all()

    feature_collection = geojson.FeatureCollection([
        geojson.Feature(geometry=geojson.loads(f.feature_geometry.geojson)) for f in spatial_features
    ])

    # geostore creation will move out of here...
    if not model_instance.geostore_id:
        rsp = requests.post(url=f'{settings.GFW_API_ROOT}/geostore', json={'geojson': feature_collection})
        if rsp.status_code == status.HTTP_200_OK:
            geostore_rsp = json.loads(rsp.text)
            model_instance.geostore_id = geostore_rsp['data']['id']

    subscribe_json = _build_subscribe_msg(model_instance)
    gfw_auth_token = model_instance.additional['gfw_auth_token']
    logger.info(f'SUBS JSON {subscribe_json}')
    rsp = requests.post(url=f'{settings.GFW_API_ROOT}/subscriptions',
                        headers={'Authorization': f'Bearer {gfw_auth_token}'},
                        json=subscribe_json,
                        timeout=5)

    logger.info(f'subscription response: {rsp} \n {rsp.text}')

    if rsp.status_code == status.HTTP_200_OK:
        model_instance.subscription_id = json.loads(rsp.text)['data']['id']
        logger.info(f'subscription successful. id: {model_instance.subscription_id}')


def fetch_subscription(model_instance): pass


def update_subscription(model_instance): pass


def delete_subscription(model_instance): pass


def _build_subscribe_msg(model):
    subsciption = dict()
    subsciption.update([
        ('name', model.name),
        ('application', 'gfw'),
        ('language', 'en')
    ])

    subsciption['datasets'] = model.additional['alert_types'],
    subsciption['resource'] = {
        'type': 'URL',
        'content': f'{get_webhook_base_url()}/{model.id.hex}/status?auth={settings.ER_APP_AUTH_TOKEN}'}
    subsciption['params'] = {'geostore': model.geostore_id}

    return subsciption

