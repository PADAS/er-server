import copy
import json
import logging
from datetime import datetime, timedelta

import pytz
import requests
from dateutil.parser import parse
from django.contrib.contenttypes.fields import GenericRelation

from tracking.models.plugin_base import Obs, TrackingPlugin, DasPluginFetchError, SourcePlugin


class VectronicsPlugin(TrackingPlugin):
    """
    Get Data from Vectronics API
    """
    DEFAULT_URL = "https://api.vectronic-wildlife.com/v2/"
    DEFAULT_SOURCE_TYPE = "collar/"
    DEFAULT_DATA_SOURCE = "gps"
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=7)
    DEFAULT_START_OFFSET = timedelta(days=140)
    # Timeout in seconds
    DEFAULT_TIMEOUT = 120

    source_plugin_reverse_relation = 'vectronicsplugin'

    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')

    @staticmethod
    def parse_date(date_string):
        # Parse date string to utc timezone format
        return pytz.utc.localize(parse(date_string))

    def _transform_to_observation(self, source, track_data):
        # Convert track_data into Observation data format
        keys = ['latitude', 'longitude']
        if track_data['latitude'] and track_data['longitude']:
            latitude = float(track_data.get('latitude'))
            longitude = float(track_data.get('longitude'))
            recorded_at = self.parse_date(track_data.get('acquisitionTime'))
            side_data = dict((k, track_data.get(k))
                             for k in track_data.keys() - keys)
            return Obs(source=source, latitude=latitude, longitude=longitude,
                       recorded_at=recorded_at, additional=side_data)
        # If latitude or longitude is not there in API Data, return None
        return None

    def fetch_observations(self, collar_id, collar_key, latest_timestamp):
        # Convert Date in iso format & Remove time zone for vectronics API
        latest_timestamp = latest_timestamp.isoformat()
        latest_timestamp = latest_timestamp.split('+')[0]

        url = (self.DEFAULT_URL + self.DEFAULT_SOURCE_TYPE + str(collar_id) +
               '/' + self.DEFAULT_DATA_SOURCE + '?collarkey={0}'.format(
            collar_key) + '&afterScts={0}'.format(latest_timestamp))
        try:
            self.logger.info(
                "SSL Verify is turned off for Vectronics API calls")
            response = requests.get(
                url, timeout=self.DEFAULT_TIMEOUT, verify=False)
            if response.status_code != 200:
                raise DasPluginFetchError("Non 200 response.")
            return json.loads(response.text)
        except requests.ConnectionError as e:
            self.logger.exception('Failed connecting to Vectronics API.')
            raise
        except requests.Timeout as e:
            self.logger.exception('Time-out connecting to Vectronics API.')
            raise
        except Exception as e:
            self.logger.exception(e)
            raise

        return None

    def fetch(self, source, cursor_data, dry_run=False):
        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}
        # Set after_date before 12 hour if latest_timestamp in cursor_data
        # Or set it before 14 days from now
        try:
            after_date = (parse(self.cursor_data['latest_timestamp']) -
                          timedelta(hours=12))
            if not after_date.tzinfo:
                after_date = after_date.replace(tzinfo=pytz.UTC)
        except Exception as e:
            after_date = datetime.now(tz=pytz.UTC) - self.DEFAULT_START_OFFSET

        latest_timestamp = None
        try:
            observations = self.fetch_observations(source.manufacturer_id,
                                                   source.additional.get(
                                                       'collar_key', ''),
                                                   after_date)
            if dry_run:
                yield observations
            if not dry_run and observations:
                for observation in observations:
                    scts = self.parse_date(observation.get('scts'))  # service-center timestamp

                    obs = self._transform_to_observation(source, observation)
                    if obs:
                        yield obs

                    # keep track of latest timestamp.
                    latest_timestamp = (max(latest_timestamp, scts) if
                                        latest_timestamp else scts)
        except Exception as e:
            self.logger.error(e)

        if latest_timestamp:  # Update cursor data.
            self.cursor_data['latest_timestamp'] = latest_timestamp.isoformat()
