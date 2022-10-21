import json
import logging
from typing import NamedTuple

from pymet import eetools

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.utils.translation import gettext_lazy as _

from activity.models import Event, EventCategory, EventType
from analyzers.base import SubjectAnalyzer
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import (CRITICAL, OK, WARNING,
                              EnvironmentalSubjectAnalyzerConfig,
                              SubjectAnalyzerResult)
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.utils import save_analyzer_event

logger = logging.getLogger(__name__)

EARTH_ENGINE_KEY_PROPERTY = 'earth_engine_json_key'


def require_earthengine(func):
    def f1(self, *args, **kwargs):

        try:
            key_dict = json.loads(
                self.config.additional[EARTH_ENGINE_KEY_PROPERTY])
            eetools.initialize_earthengine(key_dict)
        except KeyError:
            msg = f'Unable to initialize Earth Engine API without a value for "{EARTH_ENGINE_KEY_PROPERTY}".'
            logger.warning(msg)
            raise ValueError(msg)
        except Exception:
            logger.exception('Unable to initialize Earth Engine API.')
            raise
        else:
            return func(self, *args, **kwargs)

    return f1


class EventTypeSpec(NamedTuple):
    value: str
    display: str
    schema: dict = None
    icon: str = None


ENVIRONMENTAL_VALUE_SCHEMA = {
    "schema":
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Empty Event Schema",
            "type": "object",
            "properties": {
                "name": {
                    "type": "string", "title": "Subject Name"
                },
                "environmental_descriptor": {
                    "type": "string", "title": "Environmental Descriptor",
                },
                "mean_value": {
                    "type": "number", "title": "Mean Value",
                },
                "img_name": {
                    "type": "string", "title": "Earth Engine Image Name",
                },
                "img_band_name": {
                    "type": "string", "title": "Image Band Name",
                },
                "total_fix_count": {
                    "type": "number", "title": "Total Fix Count"
                },
            }
        },
    "definition": [
        "name",
        "environmental_descriptor",
        "mean_value",
        "total_fix_count",
        "img_name",
        "img_band_name",
    ]
}
ENVIRONMENTAL_ALL_CLEAR_SCHEMA = {
    "schema":
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Empty Event Schema",
            "type": "object",
            "properties": {}
        },
    "definition": []
}

EnvironmentalValueEventType = EventTypeSpec(
    value="environmental_value",
    display="Environmental Value",
    schema=ENVIRONMENTAL_VALUE_SCHEMA,
)
EnvironmentalAllClearEventType = EventTypeSpec(
    value="environmental_all_clear",
    display="Environmental All Clear",
    schema=ENVIRONMENTAL_ALL_CLEAR_SCHEMA,
)


def ensure_environmental_event_types():
    ec, created = EventCategory.objects.get_or_create(
        value='analyzer_event', defaults=dict(display='Analyzer Events'))

    for et in [EnvironmentalValueEventType, EnvironmentalAllClearEventType]:
        EventType.objects.get_or_create(value=et.value, category=ec,
                                        defaults=dict(display=et.display, schema=json.dumps(et.schema, indent=2,
                                                                                            default=str)))


class EnvironmentalAnalyzer(SubjectAnalyzer):

    def __init__(self, subject, config):
        SubjectAnalyzer.__init__(self, subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject):
        subject_groups = subject.get_ancestor_subject_groups()
        for ac in EnvironmentalSubjectAnalyzerConfig.objects.filter(
                subject_group__in=subject_groups, is_active=True):
            yield cls(subject=subject, config=ac)

    def default_observations(self):
        """
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        """
        # observations get passed back in temporally descending order
        if self.config.search_time_hours <= 0:
            return list(self.subject.observations())
        else:
            return list(self.subject.observations(last_hours=self.config.search_time_hours))

    @require_earthengine
    def analyze_trajectory(self, traj=None):
        """
        TODO: Add description.

        """

        fixes = traj.relocs.get_fixes('DESC')

        # Check to see if we have at least some data within the search time
        if len(fixes) == 0:
            raise InsufficientDataAnalyzerException

        # Create the analyzer result
        result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                       level=OK,
                                       title=self.subject.name + str(_(': low ' +
                                                                       self.config.short_description)),
                                       message=self.subject.name + str(_(' is in a low ' +
                                                                         self.config.short_description + ' area.')),
                                       analyzer_revision=1,
                                       subject=self.subject)

        # Define the latest fix as the estimated time
        result.estimated_time = fixes[0].fixtime

        # Define the geometry to be the latest fix geometry
        result.geometry_collection = DjangoGeoColl([DjangoPoint(fixes[0].ogr_geometry.GetX(),
                                                                fixes[0].ogr_geometry.GetY())])

        mean_value = eetools.extract_point_values_from_image(relocs=traj.relocs,
                                                             img_name=self.config.GEE_img_name,
                                                             band_name=self.config.GEE_img_band_name,
                                                             scale=self.config.scale_meters)

        if mean_value is not None:

            result.values = {
                'environmental_descriptor': self.config.short_description,
                'mean_value': mean_value,
                'img_name': self.config.GEE_img_name,
                'img_band_name': self.config.GEE_img_band_name,
                'total_fix_count': len(fixes),
            }

            if mean_value > self.config.threshold_value:
                # Modify analyzer result
                result.level = CRITICAL
                result.title = self.subject.name + str(_(': high ' +
                                                         self.config.short_description))
                result.message = self.subject.name + \
                    str(_(' is in a high ' + self.config.short_description + ' area.'))
        return [result, ]

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()

            if last_result is not None:
                # Save the result if there was a transition from
                # Critical/Warning to OK
                if (this_result.level is OK) and (last_result.level in (CRITICAL, WARNING)):
                    this_result.save()

    def create_analyzer_event(self, last_result=None, this_result=None):
        # no data to create an event so exit
        if not this_result:
            return

        event_data = None

        ensure_environmental_event_types()

        event_details = {'name': self.subject.name}
        event_details.update(this_result.values)

        # Create a dict() location to satisfy our EventSerializer.
        event_location_value = {
            'longitude': this_result.geometry_collection[0].x,
            'latitude': this_result.geometry_collection[0].y
        }

        # Notify if result is critical or warning
        if this_result.level in (CRITICAL, WARNING):

            # Guard against rapid fire repeated events.
            if any((
                last_result is None,
                last_result and this_result.level != last_result.level,
                last_result and (this_result.estimated_time > last_result.estimated_time))
            ):
                event_data = dict(
                    title=this_result.title,
                    event_time=this_result.estimated_time,
                    provenance=Event.PC_ANALYZER,
                    event_type=EnvironmentalValueEventType.value,  # environmental_value
                    priority=EVENT_PRIORITY_MAP.get(
                        this_result.level, Event.PRI_URGENT),
                    location=event_location_value,
                    event_details=event_details,
                    related_subjects=[{'id': self.subject.id}, ],
                )

        # Notify if there is a state transition from Critical/Warning back to
        # OK
        elif last_result is not None and (
                last_result.level in (CRITICAL, WARNING)) and this_result.level is OK:
            event_data = dict(
                title=this_result.title,
                time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type=EnvironmentalAllClearEventType.value,  # environment_all_clear
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_REFERENCE),
                location=event_location_value,
                event_details=this_result.values,
                related_subjects=[{'id': self.subject.id}, ],
            )

        if event_data:
            return save_analyzer_event(event_data)
