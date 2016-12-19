import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, LineString, MultiLineString
from django.core.exceptions import ObjectDoesNotExist

from activity.models import EventType
from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL
from ..exceptions import InsufficientDataAnalyzerException
from mapping.models import FeatureType, LineFeature

import pymet


logger = logging.getLogger(__name__)


class GeofenceAnalyzer(Analyzer):
    """ Analyzer for Track for geofence crossing """

    @property
    def event_type(self):
        return EventType.objects.get_by_value('analyzer_geofence')

    fence = models.ForeignKey(
        to=LineFeature,
        on_delete=models.CASCADE,
        null=True
    )

    is_two_state = False

    # default equator
    _default_fence = MultiLineString(
        LineString((
            (0,0),
            (90, 0),
            (180, 0),
            (270, 0),
            (0, 0),
        ))
    )

    @property
    def fence_or_default(self):
        if self.fence:
            return self.fence
        else:
            # create the objects, but we don't need to save() them
            feature_type = FeatureType(name='')

            fence = LineFeature(
                presentation={},
                feature_geometry=self._default_fence,
                type=feature_type
            )
            return fence

    def analyze(self, track):
        """ analyze track for geofence containment. Only the most recent
        two observations are considered """
        super().analyze(track)

        if len(track) < 2:
            raise InsufficientDataAnalyzerException

        last_points = track[-2:]

        track_segment = MultiLineString(
            LineString((
                Point(last_points[0].x, last_points[0].y),
                Point(last_points[1].x, last_points[1].y),
            ))
        )

        fence = self.fence_or_default

        result = AnalyzerResult(self)
        result.analyzer_type = self.__class__.__name__
        result.level = NOMINAL

        if track_segment.intersects(fence.feature_geometry):
            # determine crossing point
            crossing_point = track_segment.intersection(fence.feature_geometry)

            # determine crossing time by assuming constant speed between last two points
            p1, p2 = Point(track_segment[0][0]), Point(track_segment[0][1])

            segment_distance_to_crossing = p1.distance(crossing_point)
            segment_length = p1.distance(p2)
            normalized_distance_to_crossing = segment_distance_to_crossing / segment_length
            segment_times = track.times[-2:]
            dt = normalized_distance_to_crossing * \
                (segment_times[1] - segment_times[0]).to_pytimedelta()
            crossing_time = segment_times[0] + dt

            result.value = str(crossing_time)
            result.location = crossing_point
            result.level = CRITICAL
            result.title = 'Crossed fence'
            logger.debug(result.title)
        else:
            result.location = track[-1]
            result.value = str(track.geo_series.index[-1].to_datetime())
            result.title = 'Clear of fence'
            logger.debug(result.title)

        return result

    def analyze_jake(self, traj, geofence_analysis_params):
        """
        A function to analyze the trajectory of a subject in relation to a set of virtual fences and regions to
        determine where/when the polylines were crossed and what the containment of the individual was before and
        after any geofence crossings

        TODO: Need DAS to hydrate the trajectory object for a given subject before calling this function. DAS
        also needs to create the geofence_analysis_params object and figure out which fences to compare with this
        Subject's trajectory as well as pull in the region geometries to compare for containment

        TODO: Need to think about the analyzer framework to handle situation where multiple events are created
        from a single analysis. E.g., here, a trajectory might cross a fence in more than one place and generate
        multiple breaks.

        TODO: Does DAS really need a Null (Nominal?) result if no fences are crossed?

        TODO: Extend the DAS Geofence Analyzer Result to include these values:

        :param traj: a pymet.base.Trajectory with only two points
        :param geofence_analysis_params: a pymet.geofence.GeofenceAnalysisParam object containing the virtual fence and
        regions to check containment against
        :return: a list of DAS analyzer_geofence Results

        """

        if traj.getRelocationsFixCount() < 2:
            raise InsufficientDataAnalyzerException

        #Generate a list of crossings
        cross_results = pymet.geofence.GeofenceAnalysis.calculateGeofenceCrossings(geofence_analysis_params, [traj])

        das_analyzer_results=[]
        for cross in cross_results.getGeofenceCrossings():
            #Create a DAS Analyser result based on each crossing event
            result = AnalyzerResult(self)
            result.analyzer_type = self.__class__.__name__
            result.value = str(cross.getEstimatedCrossFix().getFixtime())
            result.location = cross.getEstimatedCrossFix().getGeoPoint().getOGRPoint() #TODO Should be Django point?
            result.level = CRITICAL
            result.title = 'Crossed fence'
            das_analyzer_results.append(result)
            logger.debug(result.title)

        return das_analyzer_results






