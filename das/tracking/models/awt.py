import copy
import logging
from datetime import datetime, timedelta

import pytz
import requests
from dateutil.parser import parse
from django.contrib.gis.db import models
from django.core.cache import cache

from tracking.models.plugin_base import Obs, TrackingPlugin, DasPluginFetchError


class AwtClient(object):
    key_mapping = {'start_time': 'T1', 'end_time': 'T2',
                   'manufacture_id': 'T', 'unit': 'U'}

    def __init__(self, host=None, username=None, password=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        self.APIS = {"LIVE_API": "/Scripts/php/api/data.php",
                     "REPLAY_API": "/Scripts/php/api/replay.php",
                     "HISTORY_API": "/Scripts/php/api/history.php",
                     "TOKEN_API": "/Scripts/php/api/token.php",
                     "TAG_API": "/Scripts/php/api/taglist.php",
                     "UNIT_API": "/Scripts/php/api/unitlist.php"
                     }
        self.username = username
        self.password = password
        self.host = host
        self.token_creation_time = datetime.now()
        self.session_token = None

    @staticmethod
    def decrypt_response(response):
        response = [{"unit_id": "AWTIRDMVAPU774", "tag_id": 1000,
                     "alarms": {"TrackMode": "false", "Battery": "false",
                                "Geofence": "false", "Coverage": "false",
                                "Memory": "false", "CBit": "false",
                                "Movement": "Unknown", "Tamperfoil": "false"},
                     "batt": 3.6, "temperature": 32, "timestamp": 1536852710,
                     "lat": -12.18578, "lon": 54.726135, "dop": 1, "speed": 0,
                     "accelerometer": {"X": 7475, "Y": 3601, "Z": 2099},
                     "log_interval": "Every1hour"},
                    {"unit_id": "AWTIMCVAP743", "tag_id": 1224124,
                     "alarms": {"TrackMode": "false", "Battery": "false",
                                "Geofence": "false", "Coverage": "true",
                                "Memory": "false", "CBit": "false",
                                "Movement": "Unknown", "Tamperfoil": "false"},
                     "batt": 7, "temperature": "Unknown",
                     "timestamp": 1536863432, "lat": -37.926348333333,
                     "lon": 29.843266666667, "dop": 0, "speed": 0,
                     "accelerometer": {"X": "Unknown", "Y": "Unknown",
                                       "Z": "Unknown"}, "log_interval": "Off"}]
        return response

    def handle_request(self, url, payload):
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        try:
            response = requests.post(url=url, headers=headers, data=payload)
            if response.status_code == 200:
                return self.decrypt_response({'a': 1})
                # return json.loads(response.text.strip())
        except requests.ConnectionError as e:
            self.logger.exception('Failed connecting to Vectronics API.')
            raise
        except requests.Timeout as e:
            self.logger.exception('Time-out connecting to Vectronics API.')
            raise
        except Exception as e:
            self.logger.exception(e)
            raise

    def fetch_fresh_session_token(self):
        self.check_and_update_token()
        url = self.host + self.APIS['TOKEN_API']
        payload = {'USR': self.username, 'PW': self.password}
        response = self.handle_request(url, payload)

        try:
            if response.get('Token', None):
                self.token_creation_time = datetime.now()
                self.session_token = response.get('Token', None)
            else:
                raise DasPluginFetchError("Error while getting token, response "
                                          "= {0}".format(response))
        except Exception as e:
            self.logger.error(e)
            raise DasPluginFetchError("Error while getting token, response "
                                      "= {0}".format(response))

    def check_and_update_token(self):
        if self.session_token:
            if datetime.now() - self.token_creation_time >= timedelta(
                    minutes=59):
                self.fetch_fresh_session_token()
        else:
            self.fetch_fresh_session_token()

    def fetch_data(self, additional_data=None):
        self.check_and_update_token()
        # Set Api Type (Live, Replay or History)
        api_type = 'LIVE_API'
        if additional_data and 'api_type' in additional_data.keys():
            api_type = additional_data['api_type']
            additional_data.pop('api_type')
        try:
            url = self.host + self.APIS.get(api_type.upper(), None)
        except Exception as e:
            raise e
        # ST is Key (used in awt api) for Session Token
        payload = {'ST': self.session_token}
        if additional_data and api_type.upper() in ['REPLAY_API',
                                                    'HISTORY_API']:
            extra_data = {}
            for i in additional_data.keys():
                extra_data[self.key_mapping[i]] = additional_data[i]
            payload = {**payload, **extra_data}
        response = self.handle_request(url, payload)

        try:
            if response.get('IV', None) and response.get('Ciphertext', None):
                return response
            else:
                raise DasPluginFetchError("Error while getting IV or CipherText"
                                          ", response = {0}".format(response))
        except Exception as e:
            self.logger.error(e)
            raise DasPluginFetchError("Error while getting IV or CipherText, "
                                      "response = {0}".format(response))

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

    def fetch_observations(self, additional_data):
        timeout = 300  # In Seconds
        key = 'awtplugin-observations-{username}'.format(username=self.username)
        observations = cache.get(key)
        if observations:
            for observation in observations:
                if observation['tag_id'] == additional_data['manufacure_id']:
                    yield observation
        else:
            manufacture_id = additional_data['manufacure_id']
            additional_data.pop('manufacure_id')
            observations = self.fetch_data(additional_data)
            cache.set(key, observations, timeout)
            additional_data['manufacure_id'] = manufacture_id
            self.fetch_observations(additional_data)


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
    api_host = models.CharField(max_length=100,
                                help_text='API Host for AWT service.')
    subscription_token = models.CharField(max_length=200,
                                          help_text="Subscription Token ")

    def remove_unknown(self, data):
        unknown_keys = []
        for key in data.keys():
            if data[key] != 'Unknown':
                if isinstance(data[key], dict):
                    data[key] = self.remove_unknown(data[key])
            else:
                unknown_keys.append(key)
        for key in unknown_keys:
            data.pop(key)
        return data

    def _transform_to_observation(self, source, track_data):
        # Convert track_data into Observation data format
        if track_data['lat'] and track_data['lon']:
            latitude = float(track_data.get('lat'))
            longitude = float(track_data.get('lon'))
            recorded_at = datetime.utcfromtimestamp(track_data.get('timestamp'))
            track_data.pop('lat')
            track_data.pop('lon')
            track_data.pop('timestamp')
            metadata = self.remove_unknown(track_data)
            return Obs(source=source, latitude=latitude, longitude=longitude,
                       recorded_at=recorded_at, additional=metadata)
        # If latitude or longitude is not there in API Data, return None
        return None

    @staticmethod
    def _parse_additional_data(additional_data):
        fixed_keys = ['api_type', 'start_time', 'end_time', 'manufacture_id',
                      'unit']
        if 'start_time' in additional_data.keys() and \
                'end_time' in additional_data.keys():
            if isinstance(additional_data['start_time'], datetime):
                additional_data['start_time'] = additional_data['start_time'] \
                    .timestamp()
            else:
                additional_data['start_time'] = parse(
                    additional_data['start_time']).timestamp()
            if isinstance(additional_data['end_time'], datetime):
                additional_data['end_time'] = additional_data['end_time'] \
                    .timestamp()
            else:
                additional_data['end_time'] = parse(
                    additional_data['end_time']).timestamp()
        else:
            # Raise Error if either start time or end time is missing
            if 'end_time' in additional_data.keys() or \
                    'start_time' in additional_data.keys():
                if 'start_time' in additional_data.keys():
                    raise Exception('End Date is missing.')
                else:
                    raise Exception('Start Date is missing.')

        # Remove unnecessary keys if there are any
        keys_to_remove = set(additional_data.keys()) - set(fixed_keys)
        for key in keys_to_remove:
            additional_data.pop(key, None)
        return additional_data

    def fetch(self, source, cursor_data, additional_data=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        client = AwtClient(host=self.api_host, username=self.username,
                           password=self.password)
        try:
            start_date = (parse(self.cursor_data['latest_timestamp']) -
                          timedelta(hours=12))
            if not start_date.tzinfo:
                after_date = start_date.replace(tzinfo=pytz.UTC)
        except Exception as e:
            start_date = datetime.now(tz=pytz.UTC) - self.DEFAULT_START_OFFSET

        end_date = datetime.now(tz=pytz.UTC)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}
        latest_timestamp = None
        try:
            params = {}
            if additional_data:
                params = self._parse_additional_data(additional_data)

            # Set tag value(manufacture id)
            params['manufacturer_id'] = source.manufacturer_id
            observations = client.fetch_data(params)

            if additional_data and 'dry_run' in additional_data.keys():
                if additional_data['dry_run']:
                    dry_run = True
                else:
                    dry_run = False

            if dry_run:
                yield observations

            if not dry_run and observations:
                for observation in observations:
                    fix_time = self.parse_date(observation.get(
                        'acquisitionTime'))
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
