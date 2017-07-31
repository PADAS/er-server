import pymet
from datetime import timedelta
from django.utils.translation import ugettext_lazy as _
from django.contrib.gis.geos import Point as DjangoPoint
from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from mapping.models import SpatialFeature
from activity.models import Event
from analyzers.utils import save_analyzer_event
from analyzers.models import SubjectAnalyzerResult, GeofenceAnalyzerConfig, WARNING, CRITICAL
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers import SubjectAnalyzer
import logging
logger = logging.getLogger(__name__)


class GeofenceAnalyzer(SubjectAnalyzer):

    """ Geofence analyzer to determine locations and estimated times where a subject's trajectory
     crosses a set of virtual fences.
     Return: a list of GeofenceAnalyzerResult
     """

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject):
        for ac in GeofenceAnalyzerConfig.objects.filter(subject_group__subjects=subject):
            yield cls(subject=subject, config=ac)

    ''' Hydrate GeofenceAnalysisParams'''
    def _create_geofence_analysis_param(self):

        gfs, crs = [], []

        # Get the SpatialFeatureGroupStatic containing the fences
        if self.config.geofences is not None:
            fs = self.config.geofences.get().features.all()
            for feat in fs:
                if feat.type == 'Geofence_Primary':
                    vf = pymet.geofence.Geofence(ogr_geometry=feat.feature_geometry,
                                                 fence_name=feat.name,
                                                 unique_id=feat.id,
                                                 warn_level='CRITICAL')
                    gfs.append(vf)
                elif feat.type == 'Geofence_Warning':
                    vf = pymet.geofence.Geofence(ogr_geometry=feat.feature_geometry,
                                                 fence_name=feat.name,
                                                 unique_id=feat.id,
                                                 warn_level='WARNING')
                    gfs.append(vf)

        # Get the SpatialFeatureGroupStatic containing the containment regions
        if self.config.containment_regions is not None:
            rgns = self.config.containment_regions.get().features.all()
            for feat in rgns:
                cr = pymet.base.Region(ogr_geometry=feat.feature_geometry,
                                       region_name=feat.name,
                                       unique_id=feat.id)
                crs.append(cr)

        return pymet.geofence.GeofenceAnalysisParams(geofences=gfs, regions=crs)

    def analyze_trajectory(self, traj=None):
        """
        A function to analyze the trajectory of a subject in relation to a set of virtual fences and regions to
        determine where/when the polylines were crossed and what the containment of the individual was before and
        after any geofence crossings
        """

        # Check to see if we have data that spans the threshold time otherwise impossible to calculate
        if timedelta(seconds=traj.relocs.timespan_seconds) < timedelta(seconds=self.config.threshold_time):
            raise InsufficientDataAnalyzerException

        _analysis_params = self._create_geofence_analysis_param()

        # Generate a list of crossings
        cross_results = pymet.geofence.GeofenceAnalysis.calc_crossings(_analysis_params, [traj])

        das_analyzer_results = []
        for cross in cross_results.geofence_crossings:
            # Create a DAS Analyser result based on each crossing event

            # Create the analyzer result
            result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                           message=self.subject.name,
                                           analyzer_revision=1,
                                           subject=self.subject)

            # Define the latest fix as the estimated time
            result.estimated_time = cross.est_cross_fix.fixtime

            # Define the geometry to be the latest fix geometry
            result.geometry_collection = DjangoGeoColl([DjangoPoint(cross.est_cross_fix.geopoint.ogr_geometry.GetX(),
                                                                    cross.est_cross_fix.geopoint.ogr_geometry.GetY())])
            # Set the event status level
            if cross.warn_level == 'WARNING':
                result.level = WARNING
            else:
                result.level = CRITICAL

            # Get the geofence name and final containing region names to form the analyzer result message
            vf_name = SpatialFeature.objects.get(pk=cross.geofence_id).short_name
            contain_names = []
            for contain_id in cross.end_region_ids:
                contain_names.append(SpatialFeature.objects.get(pk=contain_id).short_name)
            result.message = self.subject.name + str(_(' crossed ')) + vf_name + '.'
            if len(contain_names) > 0:
                result.message += str(_(' Subject now in: ')) + ",".join(contain_names)

            result.values = {
                'total_fix_count': traj.relocs.fix_count,
                'subject_speed_kmhr': cross.subject_speed_kmhr,
                'subject_heading': cross.subject_heading,
            }

            self.logger.info(result.message)

            das_analyzer_results.append(result)

        return das_analyzer_results

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
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
                message=this_result.message,
                event_time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='geofence',
                priority=EVENT_PRIORITY_MAP.get(this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=this_result.values,
            )

        if event_data:
            return save_analyzer_event(event_data)

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
