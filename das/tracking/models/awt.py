import sys
import random
import base64
import copy
import json
import logging
from time import sleep
from datetime import datetime, timedelta

import pytz
import requests
from Crypto.Cipher import AES
from dateutil.parser import parse
from django.contrib.gis.db import models
from django.core.cache import cache

from tracking.models.plugin_base import Obs, TrackingPlugin


class AWTPluginException(Exception):
    pass


class AWTPluginFUPBackoffException(Exception):
    pass


class AWTPluginBannedException(Exception):
    pass


class AWTPluginInvalidSessionTokenException(Exception):
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
    default_cache_expiry = 300  # 5 minutes
    use_policy_backoff = 70  # one minute + 10 seconds
    use_policy_backoff_threshold = 2
    use_policy_major_backoff = 3720  # one hour + 2 minutes
    # live api returns last 24 hours of data
    live_api_coverage = timedelta(hours=24)
    replay_api_coverage = timedelta(days=90)  # replay only goes back 90 days
    fetch_unit_data_expiry = 60  # one minute
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
                 subscription_token=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.host = host
        self.username = username
        self.password = password
        self.subscription_token = subscription_token
        self.session_token = None

    def decrypt_response(self, response):
        # Get IV and Ciphertext from response
        if response.get('IV', None):
            iv = response.get('IV', None)
            iv = bytes.fromhex(iv)
        else:
            self.logger.error('IV not in {response}'.format(response=response))
            raise Exception('IV not in {response}'.format(response=response))
        if response.get('Ciphertext', None):
            cipher_text = response.get('Ciphertext', None)
            cipher_text = base64.b64decode(cipher_text)
        else:
            raise Exception('Ciphertext not in {response}'.format(
                response=response))

        # Generate Cipher using subscription token, IV to decrypt response
        subscription_token = bytes.fromhex(self.subscription_token)
        cipher = AES.new(subscription_token, AES.MODE_CBC, iv)
        data = cipher.decrypt(cipher_text)

        data = data[:-ord(data[len(data) - 1:])].decode('utf-8')
        data = json.loads(json.loads(data))
        return data

    def make_units_token_key(self):
        return f'awtplugin-{self.username}-units'

    def make_session_token_key(self):
        return f'awtplugin-{self.username}-session_token'

    def make_use_policy_key(self, api_type):
        return f'awtplugin-{self.username}-use_policy-{api_type}'

    def make_major_backoff_key(self):
        return f'awtplugin-{self.username}-soft-ban'

    def check_use_policy(self, api_type, cache_key=None):
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
                ttl = parse(ttl)
                sleep_seconds = ttl - datetime.now(tz=pytz.UTC)
                sleep_seconds = sleep_seconds.total_seconds()
                if sleep_seconds:
                    self.logger.warning(
                        f'AWT Use Policy enforcement for {api_type} account {self.username}, sleeping {sleep_seconds} secs')
                    sleep(sleep_seconds)
                    sleep(random.uniform(1, 10))
            else:
                return
            backoff_count += 1

    def set_use_policy_api(self, api_type, major_backoff=False):
        backoff_seconds = self.use_policy_backoff if not major_backoff else self.use_policy_major_backoff
        ttl = datetime.now(tz=pytz.UTC) + timedelta(seconds=backoff_seconds)
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

        try:
            self.set_use_policy_api(api_type)
            self.logger.info(
                f'AWTPlugin API call {url} account {self.username}')
            response = requests.post(url=url, headers=headers, data=payload)
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

        # Session Token expiry in Seconds(has to be renewed in at least 1 hour)
        session_token_expiry = 3540  # 3540 seconds = 59 minutes
        return self.handle_request(api_type, url, payload, key, session_token_expiry)

    def check_and_update_token(self):
        awtplugin_data = cache.get(self.make_session_token_key())
        if awtplugin_data:
            if awtplugin_data['Result']:
                self.session_token = awtplugin_data['Token']
            else:
                raise Exception(awtplugin_data)
        else:
            self.fetch_fresh_session_token()
            self.check_and_update_token()

    def api_type_for_dates(self, params):
        api_type = self.LIVE_API
        key = f'awtplugin-{self.username}-{api_type}'
        if 'start_time' in params:
            start_time = datetime.fromtimestamp(
                params['start_time'], tz=pytz.UTC)
            now = datetime.now(tz=pytz.UTC)
            if now - start_time > self.live_api_coverage:
                # disable caching for replay and history
                key = None
                api_type = self.REPLAY_API
                if now - start_time > self.replay_api_coverage:
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
            if api_type != self.LIVE_API:
                for key, name in self.key_mapping.items():
                    if key in params:
                        payload[name] = params[key]
            response = self.handle_request(api_type, url, payload,
                                           key=cache_key,
                                           expiry_period=self.fetch_unit_data_expiry)
        if response:
            if response['Result']:
                return self.decrypt_response(response)
            raise AWTPluginException(response)
        raise AWTPluginException('Error in fetching observation Data')

    def fetch_units(self):
        api_type = 'UNIT_API'
        self.check_and_update_token()
        key = self.make_units_token_key()
        url = self.host + self.APIS.get(api_type, None)
        payload = {'ST': self.session_token}
        return self.handle_request(api_type, url, payload, key=key,
                                   expiry_period=self.default_cache_expiry)

    def fetch_tags(self):
        api_type = 'TAG_API'
        self.check_and_update_token()
        url = self.host + self.APIS.get(api_type, None)
        payload = {'ST': self.session_token}
        return self.handle_request(api_type, url, payload)

    def fetch_observations(self, params):
        tag_id = params['tag_id']
        results = self.fetch_data(params)
        return [observation for observation in results if observation['tag_id'] == tag_id]


class AwtPlugin(TrackingPlugin):
    """
    Get Data from AWT API
    """
    # DEFAULT_URL = "https://api.africawildlifetracking.com/"
    DEFAULT_REPORT_INTERVAL = timedelta(hours=1)
    DEFAULT_START_OFFSET = timedelta(days=14)

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

    def _transform_to_observation(self, source, track_data):
        # Convert track_data into Observation data format
        if track_data['lat'] and track_data['lon']:
            latitude = float(track_data.get('lat'))
            longitude = float(track_data.get('lon'))
            recorded_at = datetime.fromtimestamp(track_data.get('timestamp'),
                                                 tz=pytz.timezone('utc'))

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

    def fetch(self, source, cursor_data, additional_data=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        client = AwtClient(host=self.host, username=self.username,
                           password=self.password,
                           subscription_token=self.subscription_token)
        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}
        try:
            start_date = (parse(self.cursor_data['latest_timestamp']) -
                          timedelta(hours=12))
            if not start_date.tzinfo:
                start_date = start_date.replace(tzinfo=pytz.UTC)
        except Exception as e:
            start_date = datetime.now(tz=pytz.UTC) - self.DEFAULT_START_OFFSET
        end_date = datetime.now(tz=pytz.UTC)

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
        try:
            params = additional_data
            if additional_data:
                params = self._parse_additional_data(additional_data)
            dry_run = False
            if additional_data and 'dry_run' in additional_data.keys():
                if additional_data['dry_run'].lower() == 'true':
                    dry_run = True
            observations = client.fetch_observations(params)
            if dry_run:
                self.logger.info(observations)
            elif observations:
                for observation in observations:
                    fix_time = datetime.fromtimestamp(
                        observation.get('timestamp'), tz=pytz.timezone('utc'))
                    if fix_time < start_date:
                        continue
                    obs = self._transform_to_observation(source, observation)
                    if obs:
                        yield obs

                    # keep track of latest timestamp.
                    latest_timestamp = (max(latest_timestamp, fix_time) if
                                        latest_timestamp else fix_time)
        except Exception as e:
            self.logger.error(e)

        if latest_timestamp:  # Update cursor data.
            self.cursor_data['latest_timestamp'] = latest_timestamp.isoformat()
