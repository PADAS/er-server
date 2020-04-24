import datetime as dt
import pymet
from pymet.geofence import GeofenceAnalysis, GeofenceAnalysisParams, \
    GeofenceAnalysisResult, Geofence, GeofenceCrossing


class DasGeofenceAnalysis(GeofenceAnalysis):
    """
    Implementation of pymet.geofence.GeofenceAnalysis to use https://en.wikipedia.org/wiki/Even%E2%80%93odd_rule
    to determine if a subject crosses a geofence and keeps going.
    """

    @classmethod
    def calc_crossings(cls, geofence_analysis_params=None, trajectories=None):
        """
        Run the crossings analysis using the input fences/regions against the various
        :param geofence_analysis_params:
        :param trajectories:
        :return:
        """

        trajectories = trajectories or []

        # Test to make sure the calculation parameters are not None and the correct type
        assert type(geofence_analysis_params) is GeofenceAnalysisParams

        # Create the output analysis result object
        result = GeofenceAnalysisResult()

        # Set the start time of the analysis
        result.analysis_start = dt.datetime.utcnow()

        for traj in trajectories:
            assert type(traj) is pymet.base.Trajectory

            subject_id = traj.relocs.subject_id
            trajsegs = traj.traj_segs

            for trajseg in trajsegs:
                fences = geofence_analysis_params.geofences
                for fence in fences:
                    assert type(fence) is Geofence

                    # Attempt the intersection of the trajectory segment with the fence
                    intersect_pnts = trajseg.ogr_geometry.Intersection(
                        fence.ogr_geometry)

                    # intersect_pnts can either be None, POINT, or MULTIPOINT
                    _intersectPnts = []

                    if intersect_pnts.GetGeometryName() == 'POINT':
                        _intersectPnts.append(intersect_pnts)
                    else:
                        _intersectPnts = intersect_pnts

                    total_intersection_points = len([pt for pt in _intersectPnts])

                    # if total number of intersection points for a segment
                    # are odd, it's a legitimate crossing, add segment to the
                    # results
                    if total_intersection_points > 0 and total_intersection_points % 2 != 0:

                        for pnt in _intersectPnts:
                            # Create a GeoPoint at the crossing OGR point
                            crossing_geopoint = pymet.base.GeoPoint(x=pnt.GetX(),
                                                                    y=pnt.GetY())

                            segment_distance_to_crossing = \
                                trajseg.start_fix_geopoint.dist_to_point(pnt)

                            segment_length = trajseg.length_km * 1000.0

                            fractional_distance = 0.0
                            if segment_length > 0.0:
                                fractional_distance = segment_distance_to_crossing / segment_length

                            # Estimate the time of the break based on the fractional timespan
                            fractional_time = fractional_distance * (
                                    trajseg.end_fix.fixtime - trajseg.start_fix.fixtime)
                            crossing_time = trajseg.start_fix.fixtime + fractional_time

                            # Create an estimated geofence cross fix
                            estimated_cross_fix = pymet.base.Fix(crossing_geopoint,
                                                                 crossing_time)

                            # Determine containment of the subject before and after the crossing
                            containment_before = GeofenceAnalysis.asses_containment(
                                trajseg.start_fix_geopoint,
                                geofence_analysis_params.regions)

                            containment_after = GeofenceAnalysis.asses_containment(
                                trajseg.end_fix_geopoint,
                                geofence_analysis_params.regions)

                            # Create the output fence crossing result
                            crossing = GeofenceCrossing(subject_id=subject_id,
                                                        subject_speed=trajseg.speed_kmhr,
                                                        subject_travel_heading=trajseg.heading,
                                                        estimated_cross_fix=estimated_cross_fix,
                                                        geofence_id=fence.unique_id,
                                                        warn_level=fence.warn_level,
                                                        start_region_ids=containment_before,
                                                        end_region_ids=containment_after)

                            # Add this given crossing to the result
                            result.add_crossing(crossing)

        # Set the end time of the analysis
        result.analysis_end = dt.datetime.utcnow()

        return result