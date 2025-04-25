import copy
import json
import logging
from datetime import datetime, timedelta, timezone

import pytz
import requests
from dateutil.parser import parse as parse_date

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point

from observations.models import Observation, Source
from observations.serializers import ObservationSerializer
from tracking.models import SourcePlugin
from tracking.models.plugin_base import (
    DasPluginFetchError,
    Obs,
    SourcePlugin,
    TrackingPlugin,
)
from tracking.pubsub_registry import notify_new_tracks


class AWETelemetryClient(object):
    def __init__(self, service_url="https://www.awetelemetry.co.za", username=None, password=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        self.username = username
        self.password = password
        self.service_url = service_url

    def fetch_observations(self, collar_id, start_time, end_time=None):

        end_time = end_time or datetime.now(tz=timezone.utc)
        params = {
            "method": "unit",
            "username": self.username,
            "password": self.password,
            "ID": collar_id,
            "sdate": start_time.isoformat(),
            "edate": end_time.isoformat(),
        }

        headers = {
            "accept": "application/json",
        }

        response = requests.request(
            "GET", "{}/api/restunitquery.php".format(self.service_url), headers=headers, params=params
        )

        if response and response.status_code == 200:
            result = json.loads(response.text)
            if result and result["status"] == 200 and result.get("data"):
                yield from result["data"]
        else:
            msg = "Failed to get data from AWE Telementry API."
            extra = {}
            if response:
                extra["status_code"] = response.status_code
                extra["response_text"] = response.text
            self.logger.error(msg)
            raise DasPluginFetchError(msg)

    def latest(self):
        """
        Get latest fix for all devices connected to this account.
        :return:
        """
        params = {
            "method": "latest",
            "username": self.username,
            "password": self.password,
        }
        headers = {"accept": "application/json"}

        response = requests.request(
            "GET", "{}/api/restunitquery.php".format(self.service_url), headers=headers, params=params
        )

        if response and response.status_code == 200:
            result = json.loads(response.text)
            if result and result["status"] == 200:
                yield from result["data"]
        else:
            msg = "Failed to get all latest fixes from AWE Telemetry/AWT API."
            self.logger.error(msg)
            raise DasPluginFetchError(msg)


class AWETelemetryPlugin(TrackingPlugin):
    """
    Fetch data from Savannah Tracking API.
    """

    DEFAULT_START_OFFSET = timedelta(days=14)
    DEFAULT_REACH_BACK = timedelta(days=2)
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=7)
    EXECUTION_THROTTLE = timedelta(minutes=15)
    DEFAULT_SUBJECT_SUBTYPE = "elephant"
    DEFAULT_SOURCE_TYPE = "tracking-device"

    service_username = models.CharField(
        max_length=50, help_text="The username for querying the AWE Telemetry/AWT service."
    )
    service_password = models.CharField(
        max_length=50, help_text="The password for querying the AWE Telemetry/AWT service."
    )
    service_url = models.CharField(max_length=50, help_text="The API endpoint for the AWE Telemetry/AWT service.")

    source_plugin_reverse_relation = "awetelementryplugin"

    source_plugins = GenericRelation(
        SourcePlugin,
        content_type_field="plugin_type",
        object_id_field="plugin_id",
        related_query_name=source_plugin_reverse_relation,
        related_name="+",
    )

    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        client = AWETelemetryClient(
            username=self.service_username, password=self.service_password, service_url=self.service_url
        )

        try:
            st = parse_date(self.cursor_data["latest_timestamp"])
        except Exception:
            st = datetime.now(tz=timezone.utc) - self.DEFAULT_START_OFFSET

        lt = None
        self.logger.debug("Fetching data for collar_id %s", source.manufacturer_id)

        for fix in client.fetch_observations(source.manufacturer_id, start_time=st):
            observation = self._transform(source, fix)
            if not lt or observation.recorded_at > lt:
                lt = observation.recorded_at
            yield observation

        if lt and lt < datetime.now(tz=timezone.utc) - self.DEFAULT_START_OFFSET:
            # if we found data, but it's old, don't continue to look too far back
            lt = datetime.now(tz=timezone.utc) - self.DEFAULT_START_OFFSET
        elif not lt:
            # if we didn't find any data, set the latest timestamp to now - DEFAULT_REACH_BACK
            lt = datetime.now(tz=timezone.utc) - self.DEFAULT_REACH_BACK

        # Update cursor data.
        self.cursor_data["latest_timestamp"] = lt.isoformat()

    def _split_id(self, s):
        if " " in s:
            id, subject_name = (_.strip() for _ in s.split(" ", maxsplit=1))
        else:
            id, subject_name = (s.strip() for _ in range(2))
        return id, subject_name

    side_data_keys = (
        ("altitude", "ALT"),
        ("direction", "DIRECTION"),
        ("ext_temp", "EXT_TEMP"),
        ("hdop", "HDOP"),
        ("speed", "SPEED"),
        ("temp", "TEMP"),
        ("activity", "ACTIVITY"),
    )

    def _transform(self, source, fix):

        # DATE and TIME are naive UTC.
        recorded_at = pytz.utc.localize(parse_date("{DATE} {TIME}".format(**fix)))

        id, subject_name = self._split_id(fix["ID"])

        side_data = dict((k1, fix.get(k2)) for k1, k2 in self.side_data_keys if k2 in fix)
        side_data["subject_name"] = subject_name

        return Obs(
            source=source,
            recorded_at=recorded_at,
            latitude=float(fix.get("LAT", 0.0)),
            longitude=float(fix.get("LON", 0.0)),
            additional=side_data,
        )

    def _maintenance(self):
        self._sync_unit_info()

    def _sync_unit_info(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        client = AWETelemetryClient(
            username=self.service_username, password=self.service_password, service_url=self.service_url
        )

        # If these are indicated in the 'additional' blob, the use them.
        defaults = self.additional.get("defaults", {})

        default_subject_subtype = defaults.get("subject_subtype", self.DEFAULT_SUBJECT_SUBTYPE)

        try:

            latest = client.latest()
            for item in latest:

                model_name = self.name
                manufacturer_id, subject_name = self._split_id(item["ID"])

                src = Source.objects.ensure_source(
                    source_type=self.DEFAULT_SOURCE_TYPE,
                    provider=self.provider.provider_key,
                    manufacturer_id=manufacturer_id,
                    model_name=model_name,
                    subject={"subject_subtype_id": default_subject_subtype, "name": manufacturer_id},
                )

                # Create correlation.
                SourcePlugin.objects.create(plugin=self, source=src)

                obs = self._transform(src, item)

                # Short-circuit if we already have this observation.
                if Observation.objects.filter(source=src, recorded_at=obs.recorded_at).exists():
                    return

                location = None
                try:
                    location = Point(x=obs.longitude, y=obs.latitude)
                except:
                    location = None

                observation = {
                    "location": location,
                    "recorded_at": obs.recorded_at,
                    "source": src.id,
                    "additional": obs.additional,
                }

                serializer = ObservationSerializer(data=observation)
                if serializer.is_valid():
                    serializer.save()
                    notify_new_tracks(src.id)

        except Exception:
            self.logger.exception("Error in maintenance")
