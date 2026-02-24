import datetime as dt

import pymet
from osgeo import ogr
from pymet.geofence import (
    Geofence,
    GeofenceAnalysis,
    GeofenceAnalysisParams,
    GeofenceAnalysisResult,
    GeofenceCrossing,
)


class DasGeofenceAnalysis(GeofenceAnalysis):
    """
    Implementation of pymet.geofence.GeofenceAnalysis to use https://en.wikipedia.org/wiki/Even%E2%80%93odd_rule
    to determine if a subject crosses a geofence and keeps going.
    """

    @classmethod
    def calc_crossings(cls, geofence_analysis_params=None, trajectories=None, trigger_on_corner_clip=False):
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
        result.analysis_start = dt.datetime.now(tz=dt.timezone.utc)

        for traj in trajectories:
            assert type(traj) is pymet.base.Trajectory

            subject_id = traj.relocs.subject_id
            trajsegs = traj.traj_segs

            for trajseg in trajsegs:
                fences = geofence_analysis_params.geofences
                for fence in fences:
                    assert type(fence) is Geofence

                    # Attempt the intersection of the trajectory segment with the fence
                    intersect_pnts = trajseg.ogr_geometry.Intersection(fence.ogr_geometry)

                    # intersect_pnts can either be None, POINT, or MULTIPOINT if the geofence is a line or multi-line,
                    if intersect_pnts is None or intersect_pnts.IsEmpty():
                        continue

                    # empty or one of POINT, MULTIPOINT, LINESTRING, MULTILINESTRING, or GEOMETRYCOLLECTION.
                    _intersectPnts = []
                    if intersect_pnts.GetGeometryName() == "POINT":
                        newPoint = ogr.Geometry(ogr.wkbPoint)
                        newPoint.AddPoint(x=intersect_pnts.GetX(), y=intersect_pnts.GetY())
                        _intersectPnts.append(newPoint)
                    elif intersect_pnts.GetGeometryName() == "LINESTRING":

                        if intersect_pnts.GetPointCount() < 2:
                            continue

                        # In the case of a linestring intersection, we want to take the start and end points as the
                        # crossing points
                        newPoint1 = ogr.Geometry(ogr.wkbPoint)
                        newPoint1.AddPoint(x=intersect_pnts.GetPoint(0)[0], y=intersect_pnts.GetPoint(0)[1])
                        newPoint2 = ogr.Geometry(ogr.wkbPoint)
                        newPoint2.AddPoint(
                            x=intersect_pnts.GetPoint(intersect_pnts.GetPointCount() - 1)[0],
                            y=intersect_pnts.GetPoint(intersect_pnts.GetPointCount() - 1)[1],
                        )
                        # We add the points in reverse order because the intersections are returned in the order they
                        # are encountered along the fence, but we want them in the order they are encountered along the
                        # trajectory segment
                        _intersectPnts.append(newPoint2)
                        _intersectPnts.append(newPoint1)

                    elif intersect_pnts.GetGeometryName() == "MULTILINESTRING":
                        # For multi-line string, we want to take the start and end
                        # points of each linestring as the crossing points
                        for i in range(intersect_pnts.GetGeometryCount()):
                            linestring = intersect_pnts.GetGeometryRef(i)

                            if linestring.GetPointCount() < 2:
                                continue

                            newPoint1 = ogr.Geometry(ogr.wkbPoint)
                            newPoint1.AddPoint(x=linestring.GetPoint(0)[0], y=linestring.GetPoint(0)[1])
                            newPoint2 = ogr.Geometry(ogr.wkbPoint)
                            newPoint2.AddPoint(
                                x=linestring.GetPoint(linestring.GetPointCount() - 1)[0],
                                y=linestring.GetPoint(linestring.GetPointCount() - 1)[1],
                            )

                            # We add the points in reverse order because the intersections are returned in the order
                            # they're encountered along the fence but we want them in the order they are encountered
                            # along the trajectory segment
                            _intersectPnts.append(newPoint2)
                            _intersectPnts.append(newPoint1)

                    else:
                        _intersectPnts = intersect_pnts

                    total_intersection_points = len([pt for pt in _intersectPnts])

                    if total_intersection_points == 0:
                        continue

                    # if total number of intersection points for a segment
                    # are odd, it's a legitimate crossing, add segment to the
                    # results. If trigger_on_corner_clip is True, also include
                    # even numbers of intersections (corner clipping)
                    if total_intersection_points % 2 != 0 or trigger_on_corner_clip:

                        for pnt in _intersectPnts:
                            # Create a GeoPoint at the crossing OGR point
                            crossing_geopoint = pymet.base.GeoPoint(x=pnt.GetX(), y=pnt.GetY())

                            segment_distance_to_crossing = trajseg.start_fix_geopoint.dist_to_point(pnt)

                            segment_length = trajseg.length_km * 1000.0

                            fractional_distance = 0.0
                            if segment_length > 0.0:
                                fractional_distance = segment_distance_to_crossing / segment_length

                            # Estimate the time of the break based on the fractional timespan
                            fractional_time = fractional_distance * (
                                trajseg.end_fix.fixtime - trajseg.start_fix.fixtime
                            )
                            crossing_time = trajseg.start_fix.fixtime + fractional_time

                            # Create an estimated geofence cross fix
                            estimated_cross_fix = pymet.base.Fix(crossing_geopoint, crossing_time)

                            # Determine containment of the subject before and after the crossing
                            containment_before = GeofenceAnalysis.asses_containment(
                                trajseg.start_fix_geopoint, geofence_analysis_params.regions
                            )

                            containment_after = GeofenceAnalysis.asses_containment(
                                trajseg.end_fix_geopoint, geofence_analysis_params.regions
                            )

                            # Create the output fence crossing result
                            crossing = GeofenceCrossing(
                                subject_id=subject_id,
                                subject_speed=trajseg.speed_kmhr,
                                subject_travel_heading=trajseg.heading,
                                estimated_cross_fix=estimated_cross_fix,
                                geofence_id=fence.unique_id,
                                warn_level=fence.warn_level,
                                start_region_ids=containment_before,
                                end_region_ids=containment_after,
                            )

                            # Add this given crossing to the result
                            result.add_crossing(crossing)

        # Set the end time of the analysis
        result.analysis_end = dt.datetime.now(tz=dt.timezone.utc)

        return result
