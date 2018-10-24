import base64
import copy
import json
import logging
from datetime import datetime, timedelta

import pytz
import requests
from Crypto.Cipher import AES
from dateutil.parser import parse
from django.contrib.gis.db import models
from django.core.cache import cache

from tracking.models.plugin_base import Obs, TrackingPlugin


class AwtClient(object):
    key_mapping = {'start_time': 'T1', 'end_time': 'T2',
                   'manufacturer_id': 'T', 'unit': 'U'}

    def __init__(self, host=None, username=None, password=None,
                 subscription_token=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.APIS = {"LIVE_API": "/Scripts/php/api/data.php",
                     "REPLAY_API": "/Scripts/php/api/replay.php",
                     "HISTORY_API": "/Scripts/php/api/history.php",
                     "TOKEN_API": "/Scripts/php/api/token.php",
                     "TAG_API": "/Scripts/php/api/taglist.php",
                     "UNIT_API": "/Scripts/php/api/unitlist.php"
                     }
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
        try:
            data = data[:-ord(data[len(data) - 1:])].decode('utf-8')
            data = json.loads(json.loads(data))
            return data
        except Exception as e:
            self.logger.error(e)
            raise e

    def handle_request(self, url, payload, key=None, expiry_period=None):
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        if not expiry_period:
            expiry_period = 300  # In Seconds
        data = {'Result': False}
        description = ''
        try:
            response = requests.post(url=url, headers=headers, data=payload)
            if response.status_code == 200:
                data = json.loads(response.text.strip())
            else:
                description = 'Request status: {0}, Traceback: {1}'.format(
                    response.status_code, response.text.strip())
        except requests.ConnectionError as e:
            description = 'Connection Error for {url}'.format(url=url)
            data['e'] = e
        except requests.Timeout as e:
            description = 'Request Timeout for {url}'.format(url=url)
            data['e'] = e
        except Exception as e:
            description = str(e)
            data['e'] = e
        finally:
            if not data['Result']:
                data['error'] = description

            if key:
                cache.set(key, data, expiry_period)
            else:
                return data

            if 'e' in data.keys():
                self.logger.exception(data['e'])
                raise data['e']

    def fetch_fresh_session_token(self):
        url = self.host + self.APIS['TOKEN_API']
        payload = {'USR': self.username, 'PW': self.password}
        key = 'awtplugin-session-token'

        # Session Token expiry in Seconds(has to be renewed in at least 1 hour)
        session_token_expiry = 3540  # 3540 seconds = 59 minutes
        self.handle_request(url, payload, key, session_token_expiry)

    def check_and_update_token(self):
        awtplugin_data = cache.get('awtplugin-session-token')
        if awtplugin_data:
            if awtplugin_data['Result']:
                self.session_token = awtplugin_data['Token']
            else:
                raise Exception(awtplugin_data)
        else:
            self.fetch_fresh_session_token()
            self.check_and_update_token()

    def fetch_data(self, additional_data=None):
        self.check_and_update_token()

        # Set Api Type (Live, Replay or History)
        # api_type = 'LIVE_API'
        api_type = 'REPLAY_API'

        if additional_data and 'api_type' in additional_data.keys():
            api_type = additional_data['api_type']
        try:
            url = self.host + self.APIS.get(api_type.upper(), None)
        except Exception as e:
            raise e

        if 'api_type' not in additional_data:
            if api_type in ['REPLAY_API', 'HISTORY_API']:
                if 'unit' not in additional_data.keys():
                    response = self.fetch_units()
                    if response['Result']:
                        units = response['Unit_List']
                        unit_id = units[0].get('id', None)
                        additional_data['unit'] = unit_id
                    else:
                        raise Exception(response)
        else:
            additional_data.pop('api_type')

        # If unit is there, remove Manufacturer_id to avoid further requests
        if 'unit' in additional_data:
            if 'manufacturer_id' in additional_data:
                additional_data.pop('manufacturer_id')

        # ST is Key (used in awt api) for Session Token
        payload = {'ST': self.session_token}
        if additional_data and api_type.upper() in ['REPLAY_API',
                                                    'HISTORY_API']:
            extra_data = {}
            for i in additional_data.keys():
                extra_data[self.key_mapping[i]] = additional_data[i]
            payload = {**payload, **extra_data}
        key = 'awtplugin-observations-{username}'.format(username=self.username)
        data_expiry = 300  # In Seconds
        self.handle_request(url, payload, key, data_expiry)
        response = cache.get(key)
        if response:
            if response['Result']:
                return self.decrypt_response(response)
            else:
                raise Exception(response)
        else:
            raise Exception('Error in fetching observation Data')

    def fetch_units(self):
        self.check_and_update_token()
        url = self.host + self.APIS.get('UNIT_API', None)
        payload = {'ST': self.session_token}
        return self.handle_request(url, payload)

    def fetch_tags(self):
        self.check_and_update_token()
        url = self.host + self.APIS.get('TAG_API', None)
        payload = {'ST': self.session_token}
        return self.handle_request(url, payload)

    def fetch_observations(self, metadata):
        manufacturer_id = metadata['manufacturer_id']
        timeout = 300  # In Seconds
        key = 'awtplugin-observations-{username}'.format(username=self.username)
        observations = cache.get(key)
        if observations:
            if isinstance(observations, list):
                source_observations = []
                for observation in observations:
                    if str(observation['tag_id']) == str(manufacturer_id):
                        source_observations.append(observation)
                return source_observations
            else:
                raise Exception(observations)
        else:
            additional_data = copy.copy(metadata)
            observations = self.fetch_data(additional_data)
            cache.set(key, observations, timeout)
            return self.fetch_observations(metadata)


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
        fixed_keys = ['api_type', 'start_time', 'end_time', 'manufacturer_id',
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
            if 'manufacturer_id' not in additional_data.keys():
                additional_data['manufacturer_id'] = source.manufacturer_id
        else:
            additional_data = {'manufacturer_id': source.manufacturer_id}

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
