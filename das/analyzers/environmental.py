import logging
import pymet.base
import django.conf

eetools = None
try:
    earthengine_enabled = getattr(
        django.conf.settings, 'EARTHENGINE_ENABLED', False)
    if earthengine_enabled:
        import pymet.eetools as eetools
except AttributeError:
    pass


from django.contrib.gis.geos import Point as DjangoPoint
from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.utils.translation import ugettext_lazy as _

from analyzers.utils import save_analyzer_event
from activity.models import Event
from analyzers.models import EnvironmentalSubjectAnalyzerConfig, SubjectAnalyzerResult, OK, WARNING, CRITICAL
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.base import SubjectAnalyzer


def require_earthengine(func):

    if eetools is None:
        def f1(*args, **kwargs):
            raise ValueError(
                'This function requires Earth Engine tools, but they are not initialize.')
        return f1
    else:
        return func


class EnvironmentalAnalyzer(SubjectAnalyzer):

    def __init__(self, subject, config):
        SubjectAnalyzer.__init__(self, subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject):
        for ac in EnvironmentalSubjectAnalyzerConfig.objects.filter(subject_group__subjects=subject, is_active=True):
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

        event_details = {'name': self.subject.name}
        event_details.update(this_result.values)

        # Create a dict() location to satisfy our EventSerializer.
        event_location_value = {
            'longitude': this_result.geometry_collection[0].x,
            'latitude': this_result.geometry_collection[0].y
        }

        # Notify if result is critical or warning
        if this_result.level in (CRITICAL, WARNING):
            event_data = dict(
                title=this_result.title,
                event_time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='environmental_value',  # environmental_value
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=event_details,
            )

        # Notify if there is a state transition from Critical/Warning back to
        # OK
        elif last_result is not None and (
                last_result.level in (CRITICAL, WARNING)) and this_result.level is OK:
            event_data = dict(
                title=this_result.title,
                time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='environment_all_clear',  # environment_all_clear
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_REFERENCE),
                location=event_location_value,
                event_details=this_result.values,
                attachments=[{'target': self.subject, }]
            )

        if event_data:
            return save_analyzer_event(event_data)
