import sys
import random
import base64
import copy
import json
import logging
from time import sleep
from datetime import datetime, timedelta, timezone, date

import redis
import requests
from Crypto.Cipher import AES
from dateutil.parser import parse
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.core.cache import cache
from django.contrib.contenttypes.fields import GenericRelation
from django.conf import settings

import utils.redis as redis_utils

from tracking.models.plugin_base import Obs, TrackingPlugin, SourcePlugin, DasPluginSourceRetryError
from observations.models import Source, Subject, SubjectSource
from .utils import to_float


AWT_DEFAULT_TAG_DATETIME = datetime(
    year=2010, month=1, day=1, tzinfo=timezone.utc)


class AWTPluginException(Exception):
    pass


class AWTPluginFUPBackoffException(AWTPluginException):
    pass


class AWTPluginBannedException(AWTPluginException):
    pass


class AWTPluginInvalidSessionTokenException(AWTPluginException):
    pass


class AWTPluginDecryptionException(AWTPluginException):
    pass


class AwtClient(object):
    """
    AWT has a Fair Use policy that allows:
    Only one call of an API type per minute. If this is violated, a banned
    notice is returned at which time one hour must pass before trying again.
    For instance after making a Replay API call with one tag, the client must
    wait one minute for making another Replay API call.

    To work with these constraints, this client caches as much information
    as possible. The client also remembers the last time an API type is called
    and sleeps until the policy allows.
    """

    key_mapping = {'start_time': 'T1', 'end_time': 'T2',
                   'tag_id': 'T', 'unit': 'U'}
    # Session Token expiry in Seconds(has to be renewed in at least 1 hour)
    session_token_expiry = 600  # 10 minutes
    default_cache_expiry = 300  # 5 minutes
    use_policy_backoff = 70  # one minute + 10 seconds
    use_policy_backoff_threshold = 1
    use_policy_major_backoff = 3720  # one hour + 2 minutes
    # live api returns last 24 hours of data
    live_api_coverage = timedelta(hours=48)
    replay_api_coverage = timedelta(days=90)  # replay only goes back 90 days
    unit_tag_cache_expiry = 3600  # one hour
    fetch_unit_data_expiry = 240  # four minutes
    awt_api_lock_timeout = 300  # five minutes
    max_returned_rows = 1000  # no paging, but the max number of rows returned is 1000
    LIVE_API = 'LIVE_API'
    REPLAY_API = 'REPLAY_API'
    HISTORY_API = 'HISTORY_API'
    TOKEN_API = 'TOKEN_API'
    APIS = {LIVE_API: "/Scripts/php/api/data.php",
            REPLAY_API: "/Scripts/php/api/replay.php",
            HISTORY_API: "/Scripts/php/api/history.php",
            TOKEN_API: "/Scripts/php/api/token.php",
            "TAG_API": "/Scripts/php/api/taglist.php",
            "UNIT_API": "/Scripts/php/api/unitlist.php"
            }

    def __init__(self, host=None, username=None, password=None,
                 subscription_token=None, enable_history=False, enable_replay=False):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.host = host
        self.username = username
        self.password = password
        self.subscription_token = subscription_token
        self.session_token = None
        self.redis_client = redis.from_url(
            settings.CELERY_BROKER_URL)
        self.enable_history_api = enable_history
        self.enable_replay_api = enable_replay

    def decrypt_response(self, response):
        # Get IV and Ciphertext from response
        if response.get('Ciphertext', None):
            cipher_text = response.get('Ciphertext', None)
            cipher_text = base64.b64decode(cipher_text)
        else:
            if 'Ciphertext' not in response:
                raise AWTPluginDecryptionException(
                    f'Ciphertext not in {response}')
            return []

        if response.get('IV', None):
            iv = response.get('IV', None)
            iv = bytes.fromhex(iv)
        else:
            raise AWTPluginDecryptionException(f'IV not in {response}')

        # Generate Cipher using subscription token, IV to decrypt response
        subscription_token = bytes.fromhex(self.subscription_token)
        cipher = AES.new(subscription_token, AES.MODE_CBC, iv)
        data = cipher.decrypt(cipher_text)

        data = data[:-ord(data[len(data) - 1:])].decode('utf-8')
        data = json.loads(json.loads(data))
        return data

    def make_units_token_key(self):
        return f'awtplugin-{self.username}-units'

    def make_tags_token_key(self):
        return f'awtplugin-{self.username}-tags'

    def make_session_token_key(self):
        return f'awtplugin-{self.username}-session_token'

    def make_use_policy_key(self, api_type):
        return f'awtplugin-{self.username}-use_policy-{api_type}'

    def make_major_backoff_key(self):
        return f'awtplugin-{self.username}-soft-ban'

    def make_api_lock_key(self):
        return f'awtplugin-{self.username}-api-global-lock'

    def check_use_policy(self, api_type, cache_key=None, blocking=True):
        backoff_count = 0
        while True:
            response = cache.get(cache_key) if cache_key else None
            if response:
                return response

            if backoff_count >= self.use_policy_backoff_threshold:
                raise AWTPluginFUPBackoffException(
                    f'Account {self.username} exceeded backoff threshold for api {api_type}')

            if cache.get(self.make_major_backoff_key()):
                raise AWTPluginBannedException(
                    f'Banned in check_use_policy for account {self.username}')

            ttl = cache.get(self.make_use_policy_key(api_type))
            if ttl:
                if not blocking:
                    raise AWTPluginFUPBackoffException(
                        f'Account {self.username} exceeded backoff threshold for api {api_type}')

                ttl = parse(ttl)
                sleep_seconds = ttl - datetime.now(tz=timezone.utc)
                sleep_seconds = sleep_seconds.total_seconds()
                if sleep_seconds:
                    message = f'AWT Use Policy enforcement for {api_type} account {self.username}, retry after {sleep_seconds} secs'
                    self.logger.warning(message
                                        )
                    if self.use_policy_backoff_threshold <= 1:
                        raise DasPluginSourceRetryError(
                            retry_seconds=sleep_seconds, message=message)
                    else:
                        sleep(sleep_seconds)
            else:
                return
            backoff_count += 1

    def set_use_policy_api(self, api_type, major_backoff=False):
        backoff_seconds = self.use_policy_backoff if not major_backoff else self.use_policy_major_backoff
        ttl = datetime.now(tz=timezone.utc) + \
            timedelta(seconds=backoff_seconds)
        cache.set(self.make_use_policy_key(api_type),
                  ttl.isoformat(),
                  backoff_seconds)
        if major_backoff:
            cache.set(self.make_major_backoff_key(),
                      ttl.isoformat(),
                      backoff_seconds)

    def handle_request(self, api_type, url, payload, key=None, expiry_period=None):
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        if not expiry_period:
            expiry_period = self.default_cache_expiry

        response = self.check_use_policy(api_type, key)
        if response:
            return response

        with redis_utils.lock(self.redis_client, self.make_api_lock_key(), self.awt_api_lock_timeout, blocking=True) as l:
            if not l:
                raise AWTPluginFUPBackoffException(
                    'Failed to get lock on the awt api')

            response = self.check_use_policy(api_type, key, blocking=False)
            if response:
                return response

            try:
                self.set_use_policy_api(api_type)
                self.logger.info(
                    f'AWTPlugin API call {url} account {self.username}')
                response = requests.post(
                    url=url, headers=headers, data=payload)
            except requests.ConnectionError as e:
                description = 'Connection Error for {url}'.format(url=url)
                self.logger.warning(description)
                raise
            except requests.Timeout as e:
                description = 'Request Timeout for {url}'.format(url=url)
                self.logger.warning(description)
                raise

            self.set_use_policy_api(api_type)
            if response.status_code != 200:
                description = 'Request status: {0}, Traceback: {1}'.format(
                    response.status_code, response.text.strip())
                raise AWTPluginException(description)

            data = json.loads(response.text.strip())
            if data and data.get('Result') == False:
                reason = data.get('Reason')
                message = f'AWT API returned False, {reason} for account {self.username}'
                if reason:
                    if reason.lower().count('ban'):
                        self.set_use_policy_api(api_type, major_backoff=True)
                        raise AWTPluginBannedException(message)
                    elif reason.lower().startswith('invalid session token'):
                        self.clear_session_token()
                        raise AWTPluginInvalidSessionTokenException(message)
                raise AWTPluginException(message)

            if key:
                cache.set(key, data, expiry_period)
            return data

    def clear_session_token(self):
        self.session_token = None
        cache.delete(self.make_session_token_key())

    def fetch_fresh_session_token(self):
        api_type = 'TOKEN_API'
        url = self.host + self.APIS[api_type]
        payload = {'USR': self.username, 'PW': self.password}
        key = self.make_session_token_key()
        cache.delete(self.make_session_token_key())

        return self.handle_request(api_type, url, payload, key, self.session_token_expiry)

    def check_and_update_token(self):
        awtplugin_data = cache.get(self.make_session_token_key())
        if awtplugin_data:
            if awtplugin_data['Result']:
                self.session_token = awtplugin_data['Token']
            else:
                raise AWTPluginInvalidSessionTokenException(
                    f'Invalid token result: {awtplugin_data}')
        else:
            self.fetch_fresh_session_token()
            self.check_and_update_token()

    def api_type_for_dates(self, params):
        api_type = self.LIVE_API
        key = f'awtplugin-{self.username}-{api_type}'
        if 'start_time' in params:
            start_time = datetime.fromtimestamp(
                params['start_time'], tz=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            if now - start_time > self.live_api_coverage and (self.enable_replay_api or self.enable_history_api):
                # disable caching for replay and history
                key = None
                api_type = self.REPLAY_API
                if now - start_time > self.replay_api_coverage and self.enable_history_api:
                    api_type = self.HISTORY_API

        return api_type, key

    def fetch_data(self, params=None):
        """
        :param params:
        :return:
        """
        self.check_and_update_token()
        api_type, cache_key = self.api_type_for_dates(params)

        response = cache.get(cache_key) if cache_key else None

        if not response:
            url = self.host + self.APIS[api_type.upper()]
            # ST is Key (used in awt api) for Session Token
            payload = {'ST': self.session_token}
            if api_type == self.LIVE_API:
                payload['RT'] = datetime.now(
                    tz=timezone.utc) - self.live_api_coverage
                payload['RT'] = payload['RT'].timestamp()
            else:
                for key, name in self.key_mapping.items():
                    if key in params:
                        payload[name] = params[key]
                if 'T1' in payload and api_type == self.REPLAY_API:
                    min_start_timestamp = (datetime.now(
                        tz=timezone.utc) - self.replay_api_coverage).timestamp()
                    payload['T1'] = max(min_start_timestamp, payload['T1'])

            response = self.handle_request(api_type, url, payload,
                                           key=cache_key,
                                           expiry_period=self.fetch_unit_data_expiry)
        if response:
            if response['Result']:
                try:
                    return self.decrypt_response(response)
                except (AWTPluginDecryptionException,) as de:
                    self.logger.error(
                        f'AWT decryption failed: {de}, with payload: {payload}')
                    raise
            raise AWTPluginException(response)
        raise AWTPluginException('Error in fetching observation Data')

    def fetch_units(self):
        api_type = 'UNIT_API'
        self.check_and_update_token()
        key = self.make_units_token_key()
        url = self.host + self.APIS.get(api_type, None)
        payload = {'ST': self.session_token}
        return self.handle_request(api_type, url, payload, key=key,
                                   expiry_period=self.unit_tag_cache_expiry)

    def fetch_tags(self):
        api_type = 'TAG_API'
        self.check_and_update_token()
        key = self.make_tags_token_key()
        url = self.host + self.APIS.get(api_type, None)
        payload = {'ST': self.session_token}
        return self.handle_request(api_type, url, payload, key=key,
                                   expiry_period=self.unit_tag_cache_expiry)

    def fetch_observations(self, params):
        """Return the observations for a tag.
        Does paging if the date range is to large. The api only returns 1000 records
        at a time. So once started, page based on the latest timestamp.

        Args:
            params (dict): dictionary of parameters

        Yields:
            Obs: observation
        """
        tag_id = params['tag_id']
        start_time, end_time = datetime.fromtimestamp(
            params['start_time'], tz=timezone.utc), datetime.fromtimestamp(params['end_time'], tz=timezone.utc)
        latest_time = end_time

        while start_time < end_time:
            params['start_time'], params['end_time'] = start_time.timestamp(
            ), end_time.timestamp()
            results = self.fetch_data(params)
            for observation in results:
                if observation['tag_id'] == tag_id:
                    obs_time = datetime.fromtimestamp(observation['timestamp'],
                                                      tz=timezone.utc)
                    latest_time = obs_time if obs_time > latest_time else latest_time
                    yield observation

            start_time = latest_time if len(
                results) >= self.max_returned_rows else end_time


class AwtPlugin(TrackingPlugin):
    """
    Get Data from AWT API
    """
    # DEFAULT_URL = "https://api.africawildlifetracking.com/"
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=7)
    DEFAULT_START_OFFSET = timedelta(days=14)
    COLLAR_REACHBACK_OFFSET = timedelta(hours=48)

    # Timeout in seconds(Need to decide timeout)
    # DEFAULT_TIMEOUT = 30

    username = models.CharField(max_length=100,
                                help_text='Username for AWT service.')
    password = models.CharField(max_length=100,
                                help_text='Password for AWT service.')
    host = models.CharField(max_length=100,
                            help_text='API Host for AWT service.')
    subscription_token = models.CharField(max_length=200,
                                          help_text="Subscription Token ")

    source_plugin_reverse_relation = 'awtplugin'

    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')

    def _transform_to_observation(self, source, track_data):
        # Convert track_data into Observation data format
        if track_data['lat'] and track_data['lon']:
            latitude = float(track_data.get('lat'))
            longitude = float(track_data.get('lon'))
            recorded_at = datetime.fromtimestamp(track_data.get('timestamp'),
                                                 tz=timezone.utc)
            track_data['temperature'] = to_float(track_data.get('temperature'))
            track_data['batt'] = to_float(track_data.get('batt'))

            # Remove unnecessary keys and save remaining data in additional
            keys_to_remove = ['lat', 'lon', 'timestamp', 'tag_id']
            for key in keys_to_remove:
                track_data.pop(key)
            metadata = track_data
            return Obs(source=source, latitude=latitude, longitude=longitude,
                       recorded_at=recorded_at, additional=metadata)
        # If latitude or longitude is not there in API Data, return None
        return None

    def _parse_additional_data(self, metadata):
        additional_data = copy.copy(metadata)
        fixed_keys = ['api_type', 'start_time', 'end_time', 'tag_id',
                      'unit']
        if 'start_time' in additional_data.keys() and \
                'end_time' in additional_data.keys():
            if isinstance(additional_data['start_time'], datetime):
                start_time = additional_data['start_time'].timestamp()
            else:
                start_time = parse(additional_data['start_time']).timestamp()
            additional_data['start_time'] = int(start_time)

            if isinstance(additional_data['end_time'], datetime):
                end_time = additional_data['end_time'].timestamp()
            else:
                end_time = parse(additional_data['end_time']).timestamp()
            additional_data['end_time'] = int(end_time)
        else:
            # Raise Error if either start time or end time is missing
            if 'end_time' in additional_data.keys() or \
                    'start_time' in additional_data.keys():
                if 'start_time' in additional_data.keys():
                    raise Exception('End Date is missing.')
                else:
                    raise Exception('Start Date is missing.')

        # Remove unnecessary keys if there are any
        keys_to_remove = list(set(additional_data.keys()) - set(fixed_keys))
        for key in fixed_keys:
            if key in additional_data.keys() and not additional_data[key]:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            additional_data.pop(key, None)
        return additional_data

    def _get_client(self, additional_data={}):
        enable_history = additional_data.get('enable_history', False)
        enable_replay = additional_data.get('enable_replay', False)
        use_policy_backoff_threshold = additional_data.get(
            'use_policy_backoff_threshold', None)
        client = AwtClient(host=self.host, username=self.username,
                           password=self.password,
                           subscription_token=self.subscription_token,
                           enable_replay=enable_replay,
                           enable_history=enable_history)
        if use_policy_backoff_threshold:
            client.use_policy_backoff_threshold = use_policy_backoff_threshold
        return client

    def fetch(self, source, cursor_data, additional_data={}):
        self.logger = logging.getLogger(self.__class__.__name__)

        client = self._get_client(additional_data=additional_data)

        end_date = datetime.now(tz=timezone.utc)
        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}
        try:
            start_date = (parse(self.cursor_data['latest_timestamp']) -
                          COLLAR_REACHBACK_OFFSET)
            if not start_date.tzinfo:
                start_date = start_date.replace(tzinfo=timezone.utc)
        except Exception as e:
            start_date = datetime.now(
                tz=timezone.utc) - self.DEFAULT_START_OFFSET

        # Set tag value(manufacture id) if not in additional_data
        if additional_data:
            additional_data['tag_id'] = int(source.manufacturer_id)
        else:
            additional_data = {'tag_id': int(source.manufacturer_id)}

        # Set default api_type as LIVE API
        if 'start_time' not in additional_data.keys():
            additional_data['start_time'] = start_date
        if 'end_time' not in additional_data.keys():
            additional_data['end_time'] = end_date

        latest_timestamp = None
        params = additional_data
        if additional_data:
            params = self._parse_additional_data(additional_data)

        for observation in client.fetch_observations(params):
            fix_time = datetime.fromtimestamp(
                observation.get('timestamp'), tz=timezone.utc)
            obs = self._transform_to_observation(source, observation)
            if obs:
                yield obs

            # keep track of latest timestamp.
            latest_timestamp = (max(latest_timestamp, fix_time) if
                                latest_timestamp else fix_time)

        if latest_timestamp:  # Update cursor data.
            self.cursor_data['latest_timestamp'] = latest_timestamp.isoformat()

    def _maintenance(self):
        self._sync_unit_info()

    def _sync_unit_info(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        client = self._get_client()
        taglist = client.fetch_tags()["Tag_List"]
        #  {"id": 1143963, "type": "Inmarsat Satellite"},
        for tag in taglist:
            try:
                name = id = str(tag['id'])
                src, created = ensure_source(
                    'tracking-device', id, tag['type'])
                if created:
                    self.logger.info(
                        f"Created source for tag {id}, now creating plugin")
                    ensure_source_plugin(src, self)
                    ensure_subject_source(src, AWT_DEFAULT_TAG_DATETIME, name)
                    break

            except Exception as e:
                self.logger.exception(
                    f'Error in syncing tag info {tag}')
                raise


def ensure_source(source_type, manufacturer_id, model_name="AWT"):
    src, created = Source.objects.get_or_create(source_type=source_type,
                                                manufacturer_id=manufacturer_id,
                                                defaults={'model_name': model_name,
                                                          'additional': {'note': 'Created automatically during feed sync.'}})

    return src, created


def ensure_source_plugin(source, tracking_plugin):
    defaults = dict(
        status='enabled',
        # cursor_data={}
    )

    plugin_type = ContentType.objects.get_for_model(tracking_plugin)
    v, created = SourcePlugin.objects.get_or_create(defaults=defaults,
                                                    source=source,
                                                    plugin_id=tracking_plugin.id,
                                                    plugin_type=plugin_type)

    return v


def ensure_subject_source(source, event_time, subject_name=None):
    # get the most recent Subject for this Source
    subject_source = SubjectSource \
        .objects \
        .filter(source=source, assigned_range__contains=event_time)\
        .order_by('assigned_range')\
        .reverse()\
        .first()

    if not subject_source:

        subject_name = subject_name or source.manufacturer_id

        sub, created = Subject.objects.get_or_create(
            name=subject_name,
            defaults=dict(subject_subtype_id='unassigned',
                          additional=dict(region='', country='', ))
        )

        d1 = event_time
        d2 = datetime(year=9999, month=1, day=1, tzinfo=timezone.utc)
        if sub:
            subject_source, created = SubjectSource.objects.get_or_create(source=source, subject=sub,
                                                                          defaults=dict(assigned_range=(d1, d2), additional={
                                                                              'note': 'Created automatically during feed sync.'}))

    return subject_source
