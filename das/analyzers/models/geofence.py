import logging
import pymet
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.contrib.postgres.fields import JSONField

from activity.models import EventType
from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL
from ..exceptions import InsufficientDataAnalyzerException
from mapping.models import FeatureType, LineFeature, GeoFeature, FeatureSet
from observations.models import Observation, SubjectTrackSegmentFilter

logger = logging.getLogger(__name__)


class GeofenceAnalyzerResult(AnalyzerResult):

    crosstime = models.DateTimeField()
    crosspoint = models.PointField()
    analyzer = models.ForeignKey(to='GeofenceAnalyzer', on_delete=models.CASCADE)
    total_fix_count = models.IntegerField()
    observations = models.ManyToManyField(to=Observation, related_name='+')
    additional = JSONField()
    # TODO: Store the before and after containment regions
    # TODO: Store the virtual fence
    # TODO: A way to store git hash for both pymet and DAS


class GeofenceAnalyzer(Analyzer):

    """ Geofence analyzer to determine locations and estimated times where a subject's trajectory
     crosses a set of virtual fences.
     Return: a list of GeofenceAnalyzerResult
     """

    # TODO: Should be versioned

    @property
    def event_type(self):
        return EventType.objects.get_by_value('analyzer_geofence')

    virtual_fences = models.ForeignKey(
        to=FeatureSet,
        on_delete=models.CASCADE,
        null=True,
        related_name='virtualfences'
    )

    containment_regions = models.ForeignKey(
        to=FeatureSet,
        on_delete=models.CASCADE,
        null=True,
        related_name='containmentregions'
    )

    search_time_hours = models.FloatField(null=False, default=24.0)

    """ Hydrate GeofenceAnalysisParams"""
    def create_geofence_analysis_param(self):

        vfs, crs = [], []

        # Get the FeatureSet containing the fences
        if self.virtual_fences is not None:
            fs = self.virtual_fences.Feature_set.all()
            for feat in fs:
                vf = pymet.geofence.VirtualFence(ogr_geometry=feat.feature_geometry,
                                                 fence_name=feat.name,
                                                 unique_id=feat.id)
                vfs.append(vf)

        # Get the FeatureSet containing the containment regions
        if self.containment_regions is not None:
            rgns = self.containment_regions.Feature_set.all()
            for feat in rgns:
                cr = pymet.base.Region(ogr_geometry=feat.feature_geometry,
                                       region_name=feat.name,
                                       unique_id=feat.id)
                crs.append(cr)

        return pymet.geofence.GeofenceAnalysisParams(virtualfences=vfs, regions=crs)

    """Get the relevant observations for the given subject"""
    def get_observations(self):
        return self.subject.observations(last_hours=self.search_time_hours)

    """ Hydrate the trajectory """
    def create_trajectory(self):

        def create_fix(observation):
            gp = pymet.base.GeoPoint(observation.location.x, observation.location.y, 0.0)
            fix = pymet.base.Fix(gp, observation.recorded_at)
            return fix

        fixes = [create_fix(x) for x in self.get_observations()]
        relocs = pymet.base.Relocations(fixes)
        traj = pymet.base.Trajectory(relocs)

        # Look up the StraightTrackSegmentFilter settings for the given SubjectType
        traj_filter_params = SubjectTrackSegmentFilter.objects.filter(subject_type=self.subject.subject_subtype).first()
        if traj_filter_params is not None:
            traj_filter = pymet.base.TrajSegFilter(max_speed_kmhr=traj_filter_params.speed_KmHr)
            traj.traj_seg_filter = traj_filter  # Set the trajectory segment filter on the trajectory

        return traj

    def analyze(self, track=None):
        super().analyze()
        traj = self.create_trajectory()
        analysis_params = self.create_geofence_analysis_param()
        return self.analyze_jake(traj, analysis_params)

    def analyze_jake(self, traj, geofence_analysis_params):
        """
        A function to analyze the trajectory of a subject in relation to a set of virtual fences and regions to
        determine where/when the polylines were crossed and what the containment of the individual was before and
        after any geofence crossings
        """

        if traj.relocs.fix_count < 2:
            raise InsufficientDataAnalyzerException

        #Generate a list of crossings
        cross_results = pymet.geofence.GeofenceAnalysis.calc_crossings(geofence_analysis_params, [traj])

        das_analyzer_results = []
        for cross in cross_results.geofence_crossings:
            #Create a DAS Analyser result based on each crossing event
            result = GeofenceAnalyzerResult(self)
            result.analyzer_type = self.__class__.__name__
            result.analyzer = self
            result.crosstime = cross.est_cross_fix.fixtime
            result.crosspoint = Point(cross.est_cross_fix.geopoint.ogr_geometry.GetX(),
                                      cross.est_cross_fix.geopoint.ogr_geometry.GetY())
            result.total_fix_count = traj.relocs.fix_count
            result.observations = self.get_observations()
            result.title = 'Crossed virtual fence'
            das_analyzer_results.append(result)

        return das_analyzer_results


    """Original code from Joseph which I think can be deprecated"""
    """
    is_two_state = False

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

    # default equator
    _default_fence = MultiLineString(
        LineString((
            (0, 0),
            (90, 0),
            (180, 0),
            (270, 0),
            (0, 0),
            ))
            )

    def analyze_joseph(self, track):

        #analyze track for geofence containment. Only the most recent two observations are considered
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


"""



