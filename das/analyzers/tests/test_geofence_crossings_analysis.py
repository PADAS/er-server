"""
Unit tests for DasGeofenceAnalysis.calc_crossings.

These tests use pymet objects directly and require no database access.
"""

import datetime as dt

import pymet.base
from osgeo import ogr
from pymet.geofence import Geofence, GeofenceAnalysisParams

from analyzers.geofence_crossings_analysis import DasGeofenceAnalysis

UTC = dt.timezone.utc


def make_polygon_fence(coords, fence_id="test_fence"):
    """Create a Geofence from a list of (x, y) ring coordinates."""
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in coords:
        ring.AddPoint(x, y)
    polygon = ogr.Geometry(ogr.wkbPolygon)
    polygon.AddGeometry(ring)
    return Geofence(ogr_geometry=polygon, fence_name=fence_id, unique_id=fence_id)


def make_trajectory(points, subject_id="subj"):
    """Create a Trajectory from a list of ((x, y), datetime) tuples."""
    fixes = [pymet.base.Fix(geopoint=pymet.base.GeoPoint(x=x, y=y), fixtime=t) for (x, y), t in points]
    relocs = pymet.base.Relocations(fixes=fixes, subject_id=subject_id)
    return pymet.base.Trajectory(relocs=relocs)


# Square fence: (0,0)→(2,0)→(2,2)→(0,2)→(0,0)
SQUARE_FENCE_COORDS = [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]

T0 = dt.datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
T1 = dt.datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
T2 = dt.datetime(2024, 1, 1, 2, 0, tzinfo=UTC)


def calc(trajectories, fences):
    params = GeofenceAnalysisParams(geofences=fences)
    return DasGeofenceAnalysis.calc_crossings(geofence_analysis_params=params, trajectories=trajectories)


class TestPolygonFenceBoundaryOnly:
    """
    Verify that polygon geofences are intersected against their boundary only,
    so that trajectory points *inside* the polygon do not produce false crossings.
    """

    def test_crossing_into_polygon_detected(self):
        """A segment that enters the polygon produces exactly one crossing."""
        fence = make_polygon_fence(SQUARE_FENCE_COORDS)
        # (-1, 1) is outside; (1, 1) is inside — crosses the left edge at (0, 1)
        traj = make_trajectory([((-1, 1), T0), ((1, 1), T1)])
        result = calc([traj], [fence])
        assert len(result.geofence_crossings) == 1

    def test_crossing_out_of_polygon_detected(self):
        """A segment that exits the polygon produces exactly one crossing."""
        fence = make_polygon_fence(SQUARE_FENCE_COORDS)
        # (1, 1) is inside; (3, 1) is outside — crosses the right edge at (2, 1)
        traj = make_trajectory([((1, 1), T0), ((3, 1), T1)])
        result = calc([traj], [fence])
        assert len(result.geofence_crossings) == 1

    def test_segment_entirely_inside_polygon_no_crossing(self):
        """
        A segment whose both endpoints are inside the polygon must not produce
        any crossing — this is the regression case where intersecting against
        the full polygon (instead of its boundary) returned the segment itself,
        causing spurious crossing detections.
        """
        fence = make_polygon_fence(SQUARE_FENCE_COORDS)
        # (0.5, 1) and (1.5, 1) are both well inside the square
        traj = make_trajectory([((0.5, 1), T0), ((1.5, 1), T1)])
        result = calc([traj], [fence])
        assert len(result.geofence_crossings) == 0

    def test_segment_entirely_outside_polygon_no_crossing(self):
        """A segment that never touches the polygon produces no crossings."""
        fence = make_polygon_fence(SQUARE_FENCE_COORDS)
        traj = make_trajectory([((-2, 1), T0), ((-1, 1), T1)])
        result = calc([traj], [fence])
        assert len(result.geofence_crossings) == 0

    def test_through_passage_two_segments_two_crossings(self):
        """
        A subject that enters then exits across two consecutive segments
        produces two crossing events.
        """
        fence = make_polygon_fence(SQUARE_FENCE_COORDS)
        # Segment 1: outside→inside; Segment 2: inside→outside
        traj = make_trajectory([((-1, 1), T0), ((1, 1), T1), ((3, 1), T2)])
        result = calc([traj], [fence])
        assert len(result.geofence_crossings) == 2
