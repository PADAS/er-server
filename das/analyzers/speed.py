import logging
from analyzers.base import SubjectAnalyzer
from analyzers.models import LowSpeedAnalyzerConfig, SubjectAnalyzerResult, OK, CRITICAL, WARNING
from analyzers.exceptions import InsufficientDataAnalyzerException
from django.contrib.gis.geos import Point as DjangoPoint
from django.core.exceptions import ObjectDoesNotExist
from activity.models import Event
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.utils import save_analyzer_event
from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.utils.translation import ugettext_lazy as _

class LowSpeedAnalyzer(SubjectAnalyzer):

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject, config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject=None):
        for ac in LowSpeedAnalyzerConfig.objects.filter(subject_group__subjects=subject):
            yield cls(subject=subject, config=ac)

    def analyze_trajectory(self, traj=None):

        if traj is None:
            return

        # Check to see if we have at least some data within the search time
        if traj.relocs.fix_count < 2:
            raise InsufficientDataAnalyzerException

        ''' Look-up the low_speed_threshold_value from the appropriate speed distribution if it exists or use the
        default value if it doesn't'''
        low_speed_threshold_percentile = self.config.low_threshold_percentile
        low_speed_threshold_value = self.config.default_value
        if hasattr(self.subject, 'subjectspeedprofile'):
            for sd in self.subject.subjectspeedprofile.SpeedDistros.all():
                try:
                    ''' ToDo: Add logic to test whether the latest position falls within the 
                     schedule of the given speed distribution '''
                    low_speed_threshold_value = sd.percentiles[str(low_speed_threshold_percentile)]
                except KeyError:
                    low_speed_threshold_value = self.config.default_value

        # Get the relocation fixes in descending order
        fixes = traj.relocs.get_fixes('DESC')

        # Create the analyzer result
        result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                       level=OK,
                                       message=self.subject.name + str(_(' is moving normally')),
                                       analyzer_revision=1,
                                       subject=self.subject)

        # Define the latest fix as the estimated time
        result.estimated_time = fixes[0].fixtime

        # Define the geometry to be the latest fix geometry
        result.geometry_collection = DjangoGeoColl([DjangoPoint(fixes[0].ogr_geometry.GetX(),
                                                                fixes[0].ogr_geometry.GetY())])

        # Test the median speed to see whether it falls below the low-speed percentile
        current_median_speed = traj.speed_percentiles()[0.5]

        # If the last 24-hour speed is lower than the low-speed threshold then create an alarm
        if current_median_speed < low_speed_threshold_value:
            # Modify analyzer result
            result.level = CRITICAL
            result.title = self.subject.name + str(_(' is moving slowly'))
            result.message = result.title
            result.values = {
                'low_speed_threshold_percentile': low_speed_threshold_percentile,
                'low_speed_threshold_value': low_speed_threshold_value,
                'current_median_speed_value': current_median_speed,
                'total_fix_count': traj.relocs.fix_count,
            }

        self.logger.info(result.message)

        return [result]

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()

            if last_result is not None:
                # Save the result if there was a transition from Critical/Warning to OK
                if (this_result.level is OK) and (last_result.level in (CRITICAL, WARNING)):
                    this_result.save()

    def create_analyzer_event(self, last_result=None, this_result=None):

        # no data to create an event so exit
        if not this_result:
            return

        event_data = None

        # Create a dict() location to satisfy our EventSerializer.
        event_location_value = {
            'longitude': this_result.geometry_collection[0].x,
            'latitude': this_result.geometry_collection[0].y
        }

        # Notify if result is critical or warning
        if this_result.level in (CRITICAL, WARNING):
            event_data = dict(
                title=this_result.title,
                message=this_result.message,
                event_time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='analyzer_low_speed',
                priority=EVENT_PRIORITY_MAP.get(this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=this_result.values,
            )

        # Notify if there is a state transition from Critical/Warning back to OK
        elif last_result is not None and (last_result.level in (CRITICAL, WARNING)) and this_result.level is OK:
            event_data = dict(
                title=this_result.title,
                message=this_result.message,
                event_time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='analyzer_low_speed_all_clear',
                priority=EVENT_PRIORITY_MAP.get(this_result.level, Event.PRI_REFERENCE),
                location=event_location_value,
                event_details=this_result.values,
            )

        if event_data:
            return save_analyzer_event(event_data)
