import datetime as dt
import logging

import pytz
from scipy.stats import mannwhitneyu

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.utils.translation import gettext_lazy as _

from activity.models import Event
from analyzers.base import SubjectAnalyzer
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import (CRITICAL, OK, WARNING,
                              LowSpeedPercentileAnalyzerConfig,
                              LowSpeedWilcoxAnalyzerConfig,
                              SubjectAnalyzerResult)
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.utils import save_analyzer_event


class LowSpeedPercentileAnalyzer(SubjectAnalyzer):

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject, config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject=None):
        if subject:
            subject_groups = subject.get_ancestor_subject_groups()
            for ac in LowSpeedPercentileAnalyzerConfig.objects.filter(
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

    def analyze_trajectory(self, traj=None):

        if traj is None:
            return

        # Check to see if we have at least some data within the search time
        if traj.relocs.fix_count < 2:
            raise InsufficientDataAnalyzerException

        ''' Look-up the low_speed_threshold_value from the appropriate speed distribution if it exists or use the
        default value if it doesn't'''
        low_speed_threshold_percentile = self.config.low_threshold_percentile
        low_speed_threshold_value = self.config.default_low_speed_value
        if hasattr(self.subject, 'subjectspeedprofile'):
            for sd in self.subject.subjectspeedprofile.SpeedDistros.all():
                try:
                    ''' ToDo: Add logic to test whether the latest position falls within the 
                     schedule of the given speed distribution '''
                    low_speed_threshold_value = sd.percentiles[str(
                        low_speed_threshold_percentile)]
                except KeyError:
                    low_speed_threshold_value = self.config.default_low_speed_value

        # Get the relocation fixes in descending order
        fixes = traj.relocs.get_fixes('DESC')

        # Create the analyzer result
        title = self.subject.name + str(_(' is moving normally')),
        result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                       level=OK,
                                       title=title,
                                       message=title,
                                       analyzer_revision=1,
                                       subject=self.subject)

        # Define the latest fix as the estimated time
        result.estimated_time = fixes[0].fixtime

        # Define the geometry to be the latest fix geometry
        result.geometry_collection = DjangoGeoColl([DjangoPoint(fixes[0].ogr_geometry.GetX(),
                                                                fixes[0].ogr_geometry.GetY())])

        # Test the median speed to see whether it falls below the low-speed
        # percentile
        current_median_speed = traj.speed_percentiles()[0.5]

        # If the last 24-hour speed is lower than the low-speed threshold then
        # create an alarm
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
                event_type='low_speed_percentile',
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=event_details,
                related_subjects=[{'id': self.subject.id}, ],

            )

        # Notify if there is a state transition from Critical/Warning back to
        # OK
        elif last_result is not None and (last_result.level in (CRITICAL, WARNING)) and this_result.level is OK:
            event_data = dict(
                title=this_result.title,
                time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='low_speed_percentile_all_clear',
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_REFERENCE),
                location=event_location_value,
                event_details=event_details,
                related_subjects=[{'id': self.subject.id}, ],

            )

        if event_data:
            return save_analyzer_event(event_data)


class LowSpeedWilcoxAnalyzer(SubjectAnalyzer):

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject, config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject=None):
        if subject:
            subject_groups = subject.get_ancestor_subject_groups()
            for ac in LowSpeedWilcoxAnalyzerConfig.objects.filter(
                    subject_group__in=subject_groups, is_active=True):
                yield cls(subject=subject, config=ac)

    def _normal_movement_distro(self, trajectory_filter=None, end=None, last_hours=30 * 24):

        # ToDo: Add scheduling

        # Get a month of data starting one month before
        obs = self.subject.observations(last_hours=last_hours, until=end)

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.subject.default_trajectory_filter()

        # Create a Trajectory
        traj = self.subject.create_trajectory(obs, trajectory_filter)

        # Speeds segment speeds
        speeds = [seg.speed_kmhr for seg in traj.traj_segs]

        return speeds

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

    def analyze_trajectory(self, traj=None):

        if traj is None:
            return

        # Check to see if we have at least some data within the search time
        if traj.relocs.fix_count < 2:
            raise InsufficientDataAnalyzerException

        # Current speed distrbution
        cs = [seg.speed_kmhr for seg in traj.traj_segs]

        # Previous speed distribution (use only up until 30 days prior)
        ps = self._normal_movement_distro(
            end=pytz.utc.localize(dt.datetime.utcnow()) - dt.timedelta(hours=self.config.search_time_hours))

        if ps is None:
            raise InsufficientDataAnalyzerException

        if len(ps) < len(cs):
            raise InsufficientDataAnalyzerException

        # Get the relocation fixes in descending order
        fixes = traj.relocs.get_fixes('DESC')

        # Create the analyzer result
        title = self.subject.name + str(_(' is moving normally')),
        result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                       level=OK,
                                       title=title,
                                       message=title,
                                       analyzer_revision=1,
                                       subject=self.subject)

        # Define the latest fix as the estimated time
        result.estimated_time = fixes[0].fixtime

        # Define the geometry to be the latest fix geometry
        result.geometry_collection = DjangoGeoColl([DjangoPoint(fixes[0].ogr_geometry.GetX(),
                                                                fixes[0].ogr_geometry.GetY())])

        # Run the Mann-Whitney-Wilcoxon test to see if the distributions are the same
        # wilcoxon_result = ranksums(cs, ps)
        wilcoxon_result = mannwhitneyu(cs, ps, alternative='less')

        pvalue = getattr(wilcoxon_result, 'pvalue')

        # If the last 24-hour speed is lower than the previous speeds
        # distribution then create an alarm
        if pvalue < self.config.low_speed_probability_cutoff:
            # Modify analyzer result
            result.level = CRITICAL
            result.title = self.subject.name + str(_(' is moving slowly'))
            result.message = result.title
            result.values = {
                'low_speed_probability_cutoff': self.config.low_speed_probability_cutoff,
                'low_speed_probability': pvalue,
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
                event_type='low_speed_wilcoxon',
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=event_details,
                related_subjects=[{'id': self.subject.id}, ],

            )

        # Notify if there is a state transition from Critical/Warning back to
        # OK
        elif last_result is not None and (last_result.level in (CRITICAL, WARNING)) and this_result.level is OK:
            event_data = dict(
                title=this_result.title,
                time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='low_speed_wilcoxon_all_clear',
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_REFERENCE),
                location=event_location_value,
                event_details=event_details,
                related_subjects=[{'id': self.subject.id}, ],
            )

        if event_data:
            return save_analyzer_event(event_data)
