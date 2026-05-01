import json
import logging
import os
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from django_multitenant.utils import set_current_tenant

from django.contrib.gis.geos import LineString, Point, Polygon
from django.core.files import File
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from activity.models import Event, EventCategory, EventType
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import (
    FeatureProximityAnalyzerConfig,
    SubjectAnalyzerResult,
    SubjectProximityAnalyzerConfig,
)
from analyzers.proximity import FeatureProximityAnalyzer
from analyzers.subject_proximity import SubjectProximityAnalyzer
from mapping.models import (
    SpatialFeature,
    SpatialFeatureFile,
    SpatialFeatureGroupStatic,
    SpatialFeatureType,
)
from mapping.spatialfile_utils import process_spatialfile
from observations import models
from observations.models import (
    DEFAULT_ASSIGNED_RANGE,
    Observation,
    Source,
    Subject,
    SubjectGroup,
    SubjectSource,
    SubjectSubType,
    SubjectTrackSegmentFilter,
    SubjectType,
)

from ..tasks import analyze_subject_
from .analyzer_test_utils import (
    generate_observations,
    generate_random_positions,
    parse_recorded_at,
    store_observations,
)
from .proximity_test_data import OLCHODA_TRACK

logger = logging.getLogger(__name__)

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestProximityAnalyzer(TestCase):
    @classmethod
    def event_schema_json(cls):
        schema_yaml = """
            schema:
              $schema: http://json-schema.org/draft-04/schema#
              definition:
              - name
              - details
              - spatial_feature_name
              - subject_speed_kmhr
              - subject_heading
              - total_fix_count
              - proximity_dist_meters
              properties:
                name:
                  title: Name of subject
                  type: string
                details:
                  title: Details
                  type: string
                spatial_feature_name:
                  title: Spatial Feature Name
                  type: string
                subject_speed_kmhr:
                  title: Subject Speed
                  type: number
                subject_heading:
                  title: Subject Heading
                  type: number
                total_fix_count:
                  title: Total Fix Count
                  type: number
                proximity_dist_meters:
                  title: Proximity Distance Meters
                  type: number
              title: EventType Proximity
              type: object
            """
        out_json = json.dumps(yaml.load(schema_yaml, Loader=yaml.FullLoader))
        print(out_json)
        return out_json

    def setUp(self):
        set_current_tenant(self.das_tenant)

        data = File(open(os.path.join(FIXTURE_PATH, "lines.geojson"), "rb"))
        feature_types_file = File(open(os.path.join(FIXTURE_PATH, "spatial_feature_types.geojson"), "rb"))

        spatialfile = SpatialFeatureFile.objects.create(data=data, feature_types_file=feature_types_file)
        process_spatialfile(spatialfile)

        ec, created = EventCategory.objects.get_or_create(
            value="analyzer_event", defaults=dict(display="Analyzer Events")
        )

        EventType.objects.get_or_create(
            value="proximity", category=ec, defaults=dict(display="Proximity Analyzer", schema=self.event_schema_json())
        )

    def test_feature_proximity_analyzer_logic(self):
        """Test the functioning of the proximity analyzer"""

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(name="Olchoda", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="008")
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)

        sg = SubjectGroup.objects.create(
            name="proximity_subject_analyzer_group",
        )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in OLCHODA_TRACK]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        sfs = SpatialFeature.objects.filter(name__iexact="Ol Donyo Farm 2")
        logger.info("Proximity features count: %s" % str(len(sfs)))
        sf_grp = SpatialFeatureGroupStatic.objects.create(
            name="Mara Geofences (for proximity test)",
        )
        sf_grp.features.add(*sfs)
        sf_grp.save()

        # Create the Proximity Analyzer Config object
        config = FeatureProximityAnalyzerConfig.objects.create(
            subject_group=sg, threshold_dist_meters=200, proximal_features=sf_grp
        )

        # Create the analyzer
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len):
            try:
                analyzer.analyze(observations=test_observations[i - 2 : i])
            except InsufficientDataAnalyzerException:
                break

        # There should be a bunch of proximity results fom this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        self.assertTrue(len(results) > 0)
        for result in results:
            print(f"Proximity Result: {result}")

        for event in Event.objects.all():
            self.assertTrue(event.event_details.all().exists())
            ed = event.event_details.all().first().data["event_details"]
            assert ed["feature_group_name"] == sf_grp.name

        for event in Event.objects.all():
            for event_details in event.event_details.all():
                print(f"Event Details: {event_details.data}")

    def _make_proximity_feature(self):
        """Small polygon in East Africa; northern edge at lat=-1.0."""
        feature_type = SpatialFeatureType.objects.first()
        feature = SpatialFeature.objects.create(
            feature_type=feature_type,
            name="Nearby Feature",
            feature_geometry=Polygon(((34.0, -1.01), (34.01, -1.01), (34.01, -1.0), (34.0, -1.0), (34.0, -1.01))),
        )
        sf_grp = SpatialFeatureGroupStatic.objects.create(name="Proximity Feature Group")
        sf_grp.features.add(feature)
        return sf_grp

    def test_event_located_at_closest_point_on_segment_when_moving_away_from_feature(self):
        """
        Trajectory: fix A north of feature, fix B ~5 km south of feature.
        The segment A→B passes through the polygon.

        The event is placed at the closest point on the segment to the feature —
        the polygon boundary — not at the latest fix.

        Both fixes are ~5 km apart over 1 h, keeping the trajectory segment
        well under the 7 km/h SubjectTrackSegmentFilter speed limit.
        """
        sub = Subject.objects.create(name="MovingAway", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="moving_away_sg")
        sg.subjects.add(sub)

        # Feature spans lat -1.01 to -1.0, lon 34.0 to 34.01.
        # A (earlier): ~110 m north of northern edge — within 500 m threshold.
        # B (later):   ~5 km south — outside 500 m threshold.
        # Segment passes through the polygon; closest point is on polygon boundary.
        # Segment speed ≈ 5.1 km/h < 7 km/h filter limit.
        obs_a = Observation(recorded_at=timezone.now() - timedelta(hours=2), location=Point(34.005, -0.999))
        obs_b = Observation(recorded_at=timezone.now() - timedelta(hours=1), location=Point(34.005, -1.045))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Moving Away Proximity Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        FeatureProximityAnalyzer(config=config, subject=sub).analyze(observations=[obs_a, obs_b])

        events = list(Event.objects.all())
        self.assertEqual(len(events), 1)

        # Event is on the polygon boundary, not at either fix.
        event_location = events[0].location
        self.assertAlmostEqual(event_location.x, 34.005, places=3)
        self.assertTrue(
            any(abs(event_location.y - expected_y) < 1e-3 for expected_y in (-1.0, -1.01)),
            f"Expected event latitude to be on either polygon boundary intersection (-1.0 or -1.01), got {event_location.y}",
        )

    def test_event_located_at_closest_point_on_segment_when_approaching_feature(self):
        """
        Trajectory: fix A ~5 km south of feature, fix B north of feature.
        The segment A→B passes through the polygon.

        The event is placed at the closest point on the segment to the feature —
        the polygon boundary — not at either fix.

        Both fixes are ~5 km apart over 1 h, keeping the trajectory segment
        well under the 7 km/h SubjectTrackSegmentFilter speed limit.
        """
        sub = Subject.objects.create(name="Approaching", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="approaching_sg")
        sg.subjects.add(sub)

        # Feature spans lat -1.01 to -1.0, lon 34.0 to 34.01.
        # A (earlier): ~5 km south — outside 500 m threshold.
        # B (later):   ~110 m north of northern edge — within 500 m threshold.
        # Segment passes through the polygon; closest point is on polygon boundary.
        # Segment speed ≈ 5.1 km/h < 7 km/h filter limit.
        obs_a = Observation(recorded_at=timezone.now() - timedelta(hours=2), location=Point(34.005, -1.045))
        obs_b = Observation(recorded_at=timezone.now() - timedelta(hours=1), location=Point(34.005, -0.999))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Approaching Proximity Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        FeatureProximityAnalyzer(config=config, subject=sub).analyze(observations=[obs_a, obs_b])

        events = list(Event.objects.all())
        self.assertEqual(len(events), 1)

        # Event is on the polygon boundary, not at either fix.
        # The segment crosses both the southern (-1.01) and northern (-1.0) edges,
        # so nearest_points may return either intersection; accept both.
        event_location = events[0].location
        self.assertAlmostEqual(event_location.x, 34.005, places=3)
        self.assertTrue(
            any(abs(event_location.y - expected_y) < 1e-3 for expected_y in (-1.0, -1.01)),
            f"Expected event latitude to be on either polygon boundary intersection (-1.0 or -1.01), got {event_location.y}",
        )

    def test_event_fires_and_locates_correctly_for_point_feature(self):
        """
        Feature is a single point at (34.005, -1.005).
        Trajectory: A far south, B ~333 m south of the feature point (within 500 m threshold).

        The closest point on segment A→B to the point feature is B — the northern
        endpoint of the segment — because the feature lies just north of B.
        """
        sub = Subject.objects.create(name="PointApproach", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)

        feature_type = SpatialFeatureType.objects.first()
        feature = SpatialFeature.objects.create(
            feature_type=feature_type,
            name="Point Feature",
            feature_geometry=Point(34.005, -1.005),
        )
        sf_grp = SpatialFeatureGroupStatic.objects.create(name="Point Feature Group")
        sf_grp.features.add(feature)

        sg = SubjectGroup.objects.create(name="point_approach_sg")
        sg.subjects.add(sub)

        # A: ~4.1 km south of feature; B: ~333 m south of feature (within 500 m threshold).
        # Segment speed ≈ 4.1 km/h < 7 km/h filter limit.
        obs_a = Observation(recorded_at=timezone.now() - timedelta(hours=2), location=Point(34.005, -1.045))
        obs_b = Observation(recorded_at=timezone.now() - timedelta(hours=1), location=Point(34.005, -1.008))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Point Feature Proximity Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        FeatureProximityAnalyzer(config=config, subject=sub).analyze(observations=[obs_a, obs_b])

        events = list(Event.objects.all())
        self.assertEqual(len(events), 1)

        # Closest point on A→B to the point feature is B (feature is north of B).
        event_location = events[0].location
        self.assertAlmostEqual(event_location.x, obs_b.location.x, places=3)
        self.assertAlmostEqual(event_location.y, obs_b.location.y, places=3)

    def test_event_fires_and_locates_correctly_for_line_feature(self):
        """
        Feature is a horizontal line at lat=-1.005, from lon=34.0 to lon=34.01.
        Trajectory: A far south, B just north of the line (within 500 m threshold).
        The segment A→B crosses the line at (34.005, -1.005).

        The closest point on the segment to the line is the crossing point,
        so the event is placed at (34.005, -1.005).
        """
        sub = Subject.objects.create(name="LineApproach", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)

        feature_type = SpatialFeatureType.objects.first()
        feature = SpatialFeature.objects.create(
            feature_type=feature_type,
            name="Line Feature",
            feature_geometry=LineString(Point(34.0, -1.005), Point(34.01, -1.005)),
        )
        sf_grp = SpatialFeatureGroupStatic.objects.create(name="Line Feature Group")
        sf_grp.features.add(feature)

        sg = SubjectGroup.objects.create(name="line_approach_sg")
        sg.subjects.add(sub)

        # A: far south of line; B: ~444 m north of line (within 500 m threshold).
        # Segment crosses line at (34.005, -1.005). Speed ≈ 4.9 km/h < 7 km/h filter limit.
        obs_a = Observation(recorded_at=timezone.now() - timedelta(hours=2), location=Point(34.005, -1.045))
        obs_b = Observation(recorded_at=timezone.now() - timedelta(hours=1), location=Point(34.005, -1.001))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Line Feature Proximity Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        FeatureProximityAnalyzer(config=config, subject=sub).analyze(observations=[obs_a, obs_b])

        events = list(Event.objects.all())
        self.assertEqual(len(events), 1)

        # Closest point on A→B to the line is the crossing point at lat=-1.005.
        event_location = events[0].location
        self.assertAlmostEqual(event_location.x, 34.005, places=3)
        self.assertAlmostEqual(event_location.y, -1.005, places=3)

    def test_single_observation_within_threshold_fires(self):
        """
        A subject's only observation lying inside the proximity threshold must
        fire an event. pymet's segment-based proximity returns nothing for a
        single-fix trajectory, so the analyzer falls back to a direct
        point-vs-feature distance check.
        """
        sub = Subject.objects.create(name="OneFixNear", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="one_fix_near_sg")
        sg.subjects.add(sub)

        obs_only = Observation(
            recorded_at=timezone.now() - timedelta(hours=1),
            location=Point(34.005, -1.005),  # inside the feature polygon
        )

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="One Fix Near Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)
        analyzer.analyze(observations=[obs_only])

        self.assertEqual(Event.objects.count(), 1)

    def test_single_observation_outside_threshold_does_not_fire(self):
        """A subject's only observation farther than the threshold doesn't fire."""
        sub = Subject.objects.create(name="OneFixFar", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="one_fix_far_sg")
        sg.subjects.add(sub)

        # ~5 km south of the feature — far outside the 500m threshold.
        obs_only = Observation(
            recorded_at=timezone.now() - timedelta(hours=1),
            location=Point(34.005, -1.045),
        )

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="One Fix Far Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)
        analyzer.analyze(observations=[obs_only])

        self.assertEqual(Event.objects.count(), 0)

    def test_single_observation_does_not_refire_when_second_observation_arrives(self):
        """
        A subject's first observation lands inside the feature and fires (the
        single-fix code path). When a second observation arrives — also inside
        the feature — and the analyzer is re-run, it must NOT fire a duplicate
        event for the ongoing proximity streak.
        """
        sub = Subject.objects.create(name="OneThenTwoFix", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="one_then_two_fix_sg")
        sg.subjects.add(sub)

        now = timezone.now()
        # Both fixes inside the feature polygon.
        obs_1 = Observation(recorded_at=now - timedelta(hours=2), location=Point(34.005, -1.005))
        obs_2 = Observation(recorded_at=now - timedelta(hours=1), location=Point(34.005, -1.005))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="One Then Two Fix Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)

        # Run 1: only the first observation exists.
        analyzer.analyze(observations=[obs_1])
        self.assertEqual(Event.objects.count(), 1)

        # Run 2: second observation arrives, both are inside the feature.
        # The streak hasn't ended, so no new event should fire.
        analyzer.analyze(observations=[obs_1, obs_2])
        self.assertEqual(Event.objects.count(), 1)

    def test_two_observations_fires_on_transition_into_proximity(self):
        """
        A subject whose entire history is two observations — A (far) then B
        (near) — should fire exactly once for the transition into proximity.
        Exercises the 2-fix path in ``analyze_trajectory`` where there's no
        prior segment to inspect, so dedup falls through to the DB query.
        """
        sub = Subject.objects.create(name="TwoFix", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="two_fix_sg")
        sg.subjects.add(sub)

        # A: ~5 km south — outside 500 m threshold.
        # B: ~110 m north — within 500 m threshold.
        # 1 hour apart → ~5 km/h, under the 7 km/h speed filter.
        now = timezone.now()
        obs_a = Observation(recorded_at=now - timedelta(hours=2), location=Point(34.005, -1.045))
        obs_b = Observation(recorded_at=now - timedelta(hours=1), location=Point(34.005, -0.999))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Two Fix Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)
        analyzer.analyze(observations=[obs_a, obs_b])

        self.assertEqual(Event.objects.count(), 1)

    def test_only_approach_fires_not_departure(self):
        """
        Trajectory: A (far) → B (near feature) → C (far).

        Call 1: analyze([A, B])       — no prior segment, B is proximal → 1 event.
        Call 2: analyze([A, B, C])    — prior segment A→B was already proximal,
                                        so departure segment B→C is suppressed → still 1 event.

        Both adjacent segments are ~5 km apart over 1 h (≈5.1 km/h), well
        under the 7 km/h SubjectTrackSegmentFilter speed limit.
        """
        sub = Subject.objects.create(name="ApproachThenLeave", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="approach_depart_sg")
        sg.subjects.add(sub)

        # Feature northern edge at lat=-1.0.
        # A: ~5 km south — outside 500 m threshold.
        # B: ~110 m north — within 500 m threshold.
        # C: ~5 km south again — outside 500 m threshold.
        now = timezone.now()
        obs_a = Observation(recorded_at=now - timedelta(hours=3), location=Point(34.005, -1.045))
        obs_b = Observation(recorded_at=now - timedelta(hours=2), location=Point(34.005, -0.999))
        obs_c = Observation(recorded_at=now - timedelta(hours=1), location=Point(34.005, -1.045))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Approach Then Depart Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)

        # First call: only A and B available — no prior segment, B is proximal.
        analyzer.analyze(observations=[obs_a, obs_b])
        self.assertEqual(Event.objects.count(), 1)

        # Second call: all three points — prior segment A→B was proximal, so
        # departure segment B→C should not produce another event.
        analyzer.analyze(observations=[obs_a, obs_b, obs_c])
        self.assertEqual(Event.objects.count(), 1)

    def test_event_fires_when_transition_is_within_batched_observations(self):
        """
        ``handle_observation`` queues ``handle_subject`` with countdown=60 and
        relies on ``QueueOnce`` to squash a succession of tasks for the same
        subject. When several observations arrive inside that 60s window, the
        analyzer runs once on the combined batch instead of once per fix.

        If the not-proximal → proximal transition is *inside* that batch
        (i.e., not at the latest segment), the analyzer must still fire.
        Pre-fix, comparing only the latest segment against the immediate prior
        segment saw both as proximal and incorrectly suppressed. The DB-based
        dedup in ``_existing_streak_result`` now handles this directly: with
        no prior result for the feature, the run fires whether or not the
        burst extension is engaged.

        Trajectory: A, B (far) → C, D, E (near). All five observations are
        presented to the analyzer in a single ``analyze`` call to simulate the
        squashed batch.
        """
        sub = Subject.objects.create(name="BatchedTransition", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="batched_transition_sg")
        sg.subjects.add(sub)

        # Feature northern edge at lat=-1.0; threshold 500m.
        # A, B: ~5 km south — well outside threshold.
        # C, D, E: ~110-330 m north — inside threshold.
        # Adjacent fixes are spaced ≥1h apart, keeping all segments under the
        # 7 km/h SubjectTrackSegmentFilter speed limit (the largest jump,
        # B→C, is ≈4.5 km/h).
        now = timezone.now()
        obs_a = Observation(recorded_at=now - timedelta(hours=5), location=Point(34.005, -1.045))
        obs_b = Observation(recorded_at=now - timedelta(hours=4), location=Point(34.005, -1.040))
        obs_c = Observation(recorded_at=now - timedelta(hours=3), location=Point(34.005, -0.999))
        obs_d = Observation(recorded_at=now - timedelta(hours=2), location=Point(34.005, -0.998))
        obs_e = Observation(recorded_at=now - timedelta(hours=1), location=Point(34.005, -0.997))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Batched Transition Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)

        # Single call simulating all 5 obs arriving inside the 60s squash
        # window.
        analyzer.analyze(observations=[obs_a, obs_b, obs_c, obs_d, obs_e])

        self.assertEqual(Event.objects.count(), 1)

    def test_existing_event_updated_when_streak_continues(self):
        """While a proximity streak is still ongoing, subsequent analyzer runs
        update the existing event's location and metadata in place — they
        don't fire duplicates and they don't shift ``event_time``, which
        records when the streak began."""
        sub = Subject.objects.create(name="StreakUpdate", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="streak_update_sg")
        sg.subjects.add(sub)

        now = timezone.now()
        # Both fixes inside the feature polygon.
        obs_1 = Observation(recorded_at=now - timedelta(hours=2), location=Point(34.005, -1.005))
        obs_2 = Observation(recorded_at=now - timedelta(hours=1), location=Point(34.006, -1.005))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Streak Update Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)

        # Run 1: single-fix, fires the streak event.
        analyzer.analyze(observations=[obs_1])
        self.assertEqual(Event.objects.count(), 1)
        initial_event_time = Event.objects.first().event_time

        # Run 2: streak continues with a second proximal fix. The existing
        # event must be updated in place — count stays at 1, metadata
        # reflects the latest segment, and event_time stays at the original
        # streak start.
        analyzer.analyze(observations=[obs_1, obs_2])
        self.assertEqual(Event.objects.count(), 1)

        event = Event.objects.first()
        self.assertEqual(event.event_time, initial_event_time)
        details = event.event_details.first().data["event_details"]
        # Latest segment is 2-fix in Run 2 (vs 1-fix in Run 1).
        self.assertEqual(details["total_fix_count"], 2)

    def test_event_fires_when_continuous_burst_exceeds_history_window(self):
        """
        A subject that's been continuously proximal for longer than
        ``_HISTORY_FIXES`` fixes — for example, a high-frequency tracker that
        reports every second from inside a feature — must still fire on the
        first analyzer run, even though every fix in the analyzer's window is
        individually proximal so no streak boundary can be located inside it.

        Dedup falls through to the DB query in this case; with no
        ``SubjectAnalyzerResult`` yet recorded, the run fires.
        """
        sub = Subject.objects.create(name="LongBurst", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sf_grp = self._make_proximity_feature()

        sg = SubjectGroup.objects.create(name="long_burst_sg")
        sg.subjects.add(sub)

        # 12 fixes inside the feature polygon, 5 seconds apart. After the
        # ``[-_HISTORY_FIXES:]`` slice in ``analyze_trajectory`` we get 10
        # fixes, every one individually proximal — no streak boundary in the
        # window for the per-fix walk-back to find.
        now = timezone.now()
        observations = [
            Observation(
                recorded_at=now - timedelta(seconds=5 * i),
                location=Point(34.005, -1.005),
            )
            for i in range(12)
        ]
        # Pass in chronological order (oldest first) for the trajectory builder.
        observations.reverse()

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Long Burst Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)
        analyzer.analyze(observations=observations)

        self.assertEqual(Event.objects.count(), 1)

    def test_one_event_per_feature_on_sequential_approach(self):
        """
        Trajectory: A (away) → B (near F1) → C (near F2) → D (away).

        Both features are in the same feature group. Adjacent fixes are ~5 km
        apart over 1 h (≈5 km/h), well under the 7 km/h speed filter.

        Feature 1: polygon at lon 34.00-34.01, northern edge lat=-1.0.
        Feature 2: polygon at lon 34.05-34.06, northern edge lat=-1.0 (~5.5 km east).

        Call 1: analyze([A, B])
          - no prior segment; A→B proximal to F1 only → 1 event (F1)
        Call 2: analyze([A, B, C])
          - prior A→B was proximal to F1 (suppressed) but NOT F2
          - current B→C is proximal to both F1 and F2
          - → fires only for F2  (total 2 events)
        Call 3: analyze([B, C, D])
          - prior B→C was proximal to F2
          - current C→D is proximal to F2 only (F1 is ~5 km away)
          - → suppressed for F2; F1 not proximal → no new event  (total 2 events)
        """
        sub = Subject.objects.create(name="SeqApproach", subject_subtype_id="elephant")
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)

        feature_type = SpatialFeatureType.objects.first()
        feature_1 = SpatialFeature.objects.create(
            feature_type=feature_type,
            name="West Feature",
            feature_geometry=Polygon(((34.0, -1.01), (34.01, -1.01), (34.01, -1.0), (34.0, -1.0), (34.0, -1.01))),
        )
        feature_2 = SpatialFeature.objects.create(
            feature_type=feature_type,
            name="East Feature",
            feature_geometry=Polygon(((34.05, -1.01), (34.06, -1.01), (34.06, -1.0), (34.05, -1.0), (34.05, -1.01))),
        )
        sf_grp = SpatialFeatureGroupStatic.objects.create(name="Two Feature Group")
        sf_grp.features.add(feature_1, feature_2)

        sg = SubjectGroup.objects.create(name="seq_approach_sg")
        sg.subjects.add(sub)

        now = timezone.now()
        obs_a = Observation(recorded_at=now - timedelta(hours=4), location=Point(34.005, -1.045))
        obs_b = Observation(recorded_at=now - timedelta(hours=3), location=Point(34.005, -0.999))
        obs_c = Observation(recorded_at=now - timedelta(hours=2), location=Point(34.055, -0.999))
        obs_d = Observation(recorded_at=now - timedelta(hours=1), location=Point(34.055, -1.045))

        config = FeatureProximityAnalyzerConfig.objects.create(
            name="Sequential Approach Analyzer",
            subject_group=sg,
            threshold_dist_meters=500,
            proximal_features=sf_grp,
        )
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)

        analyzer.analyze(observations=[obs_a, obs_b])
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(
            Event.objects.filter(event_details__data__event_details__spatial_feature_name="West Feature").count(), 1
        )
        self.assertEqual(
            Event.objects.filter(event_details__data__event_details__spatial_feature_name="East Feature").count(), 0
        )

        analyzer.analyze(observations=[obs_a, obs_b, obs_c])
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(
            Event.objects.filter(event_details__data__event_details__spatial_feature_name="West Feature").count(), 1
        )
        self.assertEqual(
            Event.objects.filter(event_details__data__event_details__spatial_feature_name="East Feature").count(), 1
        )

        analyzer.analyze(observations=[obs_b, obs_c, obs_d])
        self.assertEqual(Event.objects.count(), 2)

    def test_subject_proximity_analyzer_logic(self):
        """Test the functioning of the proximity analyzer"""

        # Create models (Subject, SubjectSource and Source)

        # Analysis subject info
        sub = Subject.objects.create(name="Olchoda", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="008")
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sg = SubjectGroup.objects.create(
            name="elephants",
        )
        sg.subjects.add(sub)
        sg.save()

        # counter subject group info
        source2 = Source.objects.create(manufacturer_id="fatu-008")
        sub2 = Subject.objects.create(name="Fatu", subject_subtype_id="rhino")
        SubjectSource.objects.create(subject=sub2, source=source2, assigned_range=DEFAULT_ASSIGNED_RANGE)
        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="rhino", speed_KmHr=8.0)

        sg2 = SubjectGroup.objects.create(
            name="rhinos",
        )
        sg2.subjects.add(sub2)
        sg2.save()

        # Create test observations
        test_observations = [x for x in generate_random_positions()]
        for item in test_observations:
            recorded_at = item[0]
            location = item[1]
            models.Observation.objects.create(recorded_at=recorded_at, location=location, source=source, additional={})

            models.Observation.objects.create(recorded_at=recorded_at, location=location, source=source2, additional={})
        # Create the Proximty Analyzer Config object
        config = SubjectProximityAnalyzerConfig.objects.create(
            subject_group=sg, second_subject_group=sg2, threshold_dist_meters=200
        )
        analyzer = SubjectProximityAnalyzer(config=config, subject=sub)

        # Iterate through the observations adding another point to the
        # trajectory on each loop

        analyzer.analyze(observations=Observation.objects.filter(source=source))

        # There should be a bunch of proximity results fom this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        self.assertTrue(len(results) > 0)
        for result in results:
            print(f"Proximity Result: {result}")

        for event in Event.objects.all():
            self.assertTrue(event.event_details.all().exists())

        for event in Event.objects.all():
            for event_details in event.event_details.all():
                print(f"Event Details: {event_details.data}")

    def test_subject_proximity_analyzer_proximity_distance(self):
        """Test that the subject proximity analyzer returns the proximity distance"""

        # Create models (Subject, SubjectSource and Source)
        subject_chuka = Subject.objects.create(name="Chuka", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="CHK001")
        SubjectSource.objects.create(subject=subject_chuka, source=source)
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)
        sg = SubjectGroup.objects.create(
            name="elephants",
        )
        sg.subjects.add(subject_chuka)
        sg.save()

        # counter subject group info
        subject_hari = Subject.objects.create(name="Hari", subject_subtype_id="rhino")
        source2 = Source.objects.create(manufacturer_id="HR0001")
        SubjectSource.objects.create(subject=subject_hari, source=source2, assigned_range=DEFAULT_ASSIGNED_RANGE)
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="rhino", speed_KmHr=8.0)

        sg2 = SubjectGroup.objects.create(
            name="rhinos",
        )
        sg2.subjects.add(subject_hari)
        sg2.save()

        recorded_at = datetime.now(tz=timezone.utc)

        coordinates = [
            [[-122.22081899642944, 47.409590070615295], [-122.22041130065918, 47.41009832201713]],
            [[-122.22253561019896, 47.41067917475635], [-122.22317934036253, 47.40943033344746]],
            [[-122.22656965255739, 47.41295895984107], [-122.22708463668822, 47.40986597912771]],
        ]

        for coord in coordinates:
            models.Observation.objects.create(
                recorded_at=recorded_at, location=Point(coord[0][0], coord[0][1]), source=source, additional={}
            )
            models.Observation.objects.create(
                recorded_at=recorded_at, location=Point(coord[1][0], coord[1][1]), source=source2, additional={}
            )

            recorded_at = recorded_at - timedelta(minutes=10)

        config = SubjectProximityAnalyzerConfig.objects.create(
            subject_group=sg, second_subject_group=sg2, threshold_dist_meters=200
        )
        analyzer = SubjectProximityAnalyzer(config=config, subject=subject_chuka)

        # run the analyzer function.
        analyzer.analyze()

        # There should be a bunch of proximity results fom this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=subject_chuka)

        for result in results:
            print(f"Proximity Result: {result}")
            assert result.values.get("proximity_dist_meters") > 50

        for event in Event.objects.all():
            self.assertTrue(event.event_details.all().exists())

        for event in Event.objects.all():
            for event_details in event.event_details.all():
                print(f"Event Details: {event_details.data}")


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestFeatureProximityAnalyzerQuietPeriod:
    OBSERVATIONS = [
        {
            "longitude": 3.5069101510333525,
            "latitude": 9.878768920898438,
            "recorded_at": "2021-10-09T23:00:13+00:00",
        },
        {
            "longitude": 3.514449077480177,
            "latitude": 9.952239990234375,
            "recorded_at": "2021-10-09T23:30:20+00:00",
        },
        {
            "longitude": 3.5288414041434337,
            "latitude": 10.014381408691406,
            "recorded_at": "2021-10-10T00:00:24+00:00",
        },
        {
            "longitude": 3.5296177696020568,
            "latitude": 10.01674711704254,
            "recorded_at": "2021-10-10T00:00:30+00:00",
        },
    ]

    def test_proximity_quiet_period(
        self,
        subject_source,
        spatial_feature_type,
        spatial_feature_group_static,
        feature_proximity_analyzer_config,
        dummy_cache,
        caplog,
    ):
        set_current_tenant(self.das_tenant)

        caplog.set_level(logging.INFO)
        wildlife_subject_type = SubjectType.objects.get(value="wildlife")
        elephant_subject_subtype = SubjectSubType.objects.get(value="elephant")
        elephant_subject_subtype.subject_type = wildlife_subject_type
        elephant_subject_subtype.save()

        subject_source.subject.subject_subtype = elephant_subject_subtype
        subject_source.subject.save()

        subject = subject_source.subject

        subject_group = feature_proximity_analyzer_config.subject_group
        subject_group.name = "elephants"
        subject_group.save()
        subject_group.subjects.add(subject)

        spatial_feature = SpatialFeature.objects.create(
            feature_type=spatial_feature_type,
            feature_geometry=LineString(Point(3.543898, 10.009698), Point(3.505531, 10.028968)),
        )
        spatial_feature_group_static.features.add(spatial_feature)

        feature_proximity_analyzer_config.quiet_period = timedelta(0, 9000)
        feature_proximity_analyzer_config.proximal_features = spatial_feature_group_static
        feature_proximity_analyzer_config.threshold_dist_meters = 250
        feature_proximity_analyzer_config.subject_group = subject_group
        feature_proximity_analyzer_config.save()

        test_observations = [parse_recorded_at(point) for point in self.OBSERVATIONS]
        store_observations(
            observations=test_observations,
            timeshift=False,
            source=subject_source.source,
        )
        for minutes, observation in enumerate(Observation.objects.all(), 1):
            observation.recorded_at = timezone.now() - timedelta(hours=6, minutes=minutes * 15)
            observation.save()

        analyze_subject_(subject.id)

        assert f"Pausing analyzer with id={feature_proximity_analyzer_config.id}" in caplog.text
        assert f"The analyzer {feature_proximity_analyzer_config.id} is quiet for a while" not in caplog.text
        assert Event.objects.all().count() == 1

    def test_proximity_quiet_period_check_analyzer_is_paused(
        self,
        subject_source,
        spatial_feature_type,
        spatial_feature_group_static,
        feature_proximity_analyzer_config,
        dummy_cache,
        caplog,
    ):
        caplog.set_level(logging.INFO)

        wildlife_subject_type = SubjectType.objects.get(value="wildlife")
        elephant_subject_subtype = SubjectSubType.objects.get(value="elephant")
        elephant_subject_subtype.subject_type = wildlife_subject_type
        elephant_subject_subtype.save()

        subject_source.subject.subject_subtype = elephant_subject_subtype
        subject_source.subject.save()

        subject = subject_source.subject

        subject_group = feature_proximity_analyzer_config.subject_group
        subject_group.name = "elephants"
        subject_group.save()
        subject_group.subjects.add(subject)

        spatial_feature = SpatialFeature.objects.create(
            feature_type=spatial_feature_type,
            feature_geometry=LineString(Point(3.543898, 10.009698), Point(3.505531, 10.028968)),
        )
        spatial_feature_group_static.features.add(spatial_feature)

        feature_proximity_analyzer_config.quiet_period = timedelta(0, 9000)
        feature_proximity_analyzer_config.proximal_features = spatial_feature_group_static
        feature_proximity_analyzer_config.threshold_dist_meters = 250
        feature_proximity_analyzer_config.subject_group = subject_group
        feature_proximity_analyzer_config.save()

        test_observations = [parse_recorded_at(point) for point in self.OBSERVATIONS]
        store_observations(
            observations=test_observations,
            timeshift=False,
            source=subject_source.source,
        )
        for minutes, observation in enumerate(Observation.objects.all(), 1):
            observation.recorded_at = timezone.now() - timedelta(hours=6, minutes=minutes * 15)
            observation.save()

        analyze_subject_(subject.id)
        analyze_subject_(subject.id)

        assert f"Pausing analyzer with id={feature_proximity_analyzer_config.id}" in caplog.text
        assert f"The analyzer {feature_proximity_analyzer_config.id} is quiet for a while" in caplog.text
        assert Event.objects.all().count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestProximityAnalyzerConfig:
    def test_subjects_from_nested_subject_groups_are_included(
        self, subject_group_tree, subject_group_empty, five_subjects
    ):
        dist_meters_threshold = 500
        subject = five_subjects[0]
        subject_second = five_subjects[1]

        subject_group_empty.subjects.add(subject)
        subject_group_tree.children.first().subjects.add(subject_second)

        SubjectTrackSegmentFilter.objects.create(subject_subtype_id=subject.subject_subtype.value, speed_KmHr=8.0)
        if subject_second.subject_subtype != subject.subject_subtype:
            SubjectTrackSegmentFilter.objects.create(
                subject_subtype_id=subject_second.subject_subtype.value, speed_KmHr=8.0
            )

        # Create mock observations for both subjects
        source = Source.objects.create(manufacturer_id="TEST001")
        source2 = Source.objects.create(manufacturer_id="TEST002")
        SubjectSource.objects.create(subject=subject, source=source)
        SubjectSource.objects.create(subject=subject_second, source=source2)

        # Create test observations that are within proximity
        recorded_at = timezone.now()

        # Base coordinates
        base_lat = 9.878768920898438
        base_lon = 3.5069101510333525

        # Create 5 observations for each source, slightly offset but within 500m
        offsets = [
            (0, 0),  # base point
            (0.001, 0.001),  # ~156m diagonal
            (-0.001, 0.001),  # ~156m diagonal
            (0.002, -0.001),  # ~335m diagonal
            (-0.002, 0.002),  # ~400m diagonal
        ]

        for offset_lon, offset_lat in offsets:
            # Create observation for first source
            models.Observation.objects.create(
                recorded_at=recorded_at, location=Point(base_lon + offset_lon, base_lat + offset_lat), source=source
            )
            # Create observation for second source
            models.Observation.objects.create(
                recorded_at=recorded_at, location=Point(base_lon + offset_lon, base_lat + offset_lat), source=source2
            )
            # Increment time by 1 minute for next observation
            recorded_at = recorded_at + timedelta(minutes=1)

        config = SubjectProximityAnalyzerConfig.objects.create(
            subject_group=subject_group_empty,
            second_subject_group=subject_group_tree,
            threshold_dist_meters=dist_meters_threshold,
            proximity_time=2,  # this in hours
        )

        # Create and run the analyzer
        analyzer = SubjectProximityAnalyzer(config=config, subject=subject)
        analyzer.analyze(observations=Observation.objects.filter(source=source))

        results = SubjectAnalyzerResult.objects.filter(subject=subject)
        assert results.count() > 0
        for result in results:
            logger.info(f"Proximity Result: {result}")
            assert result.values.get("proximity_dist_meters") < dist_meters_threshold


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDefaultObservations:
    """Regression tests for FeatureProximityAnalyzer.default_observations().

    The analyzer fetches the 3 most recent fixes in the common case and only
    extends to a wider history when those 3 fixes fall inside the
    burst-detection window (handle_observation's 60s squash window plus a
    jitter buffer).
    """

    def _create_observations(self, source, count, interval=timedelta(minutes=1)):
        recorded_at = timezone.now()
        for i in range(count):
            Observation.objects.create(
                recorded_at=recorded_at - i * interval,
                location=Point(-103.313486, 20.420935),
                source=source,
                additional={},
            )

    def test_default_observations_non_burst_returns_three(self, subject_source, feature_proximity_analyzer_config):
        """Non-burst (fixes spaced beyond the burst window): returns exactly 3 items."""
        # 1 minute apart — well outside the 120s burst-detection window.
        self._create_observations(subject_source.source, count=5, interval=timedelta(minutes=1))

        feature_proximity_analyzer_config.search_time_hours = 0
        feature_proximity_analyzer_config.save()

        analyzer = FeatureProximityAnalyzer(subject=subject_source.subject, config=feature_proximity_analyzer_config)

        result = analyzer.default_observations()

        assert len(result) == 3

    def test_default_observations_non_burst_pushes_limit_three_to_db(
        self, subject_source, feature_proximity_analyzer_config
    ):
        """Non-burst case: DB query carries LIMIT 3 (no extension fetch)."""
        self._create_observations(subject_source.source, count=5, interval=timedelta(minutes=1))

        feature_proximity_analyzer_config.search_time_hours = 0
        feature_proximity_analyzer_config.save()

        analyzer = FeatureProximityAnalyzer(subject=subject_source.subject, config=feature_proximity_analyzer_config)

        with CaptureQueriesContext(connection) as ctx:
            analyzer.default_observations()

        combined_sql = " ".join(q["sql"] for q in ctx.captured_queries)
        assert "LIMIT 3" in combined_sql

    def test_default_observations_burst_extends_window(self, subject_source, feature_proximity_analyzer_config):
        """Burst case: 3 most recent fixes are within the burst window, so the
        fetch is extended to all observations inside the burst plus one prior
        fix."""
        # 5 obs spaced 10s apart — all 3 most recent fall inside the 120s
        # burst window. Total span ≈40s; one fix sits well before the cutoff.
        self._create_observations(subject_source.source, count=5, interval=timedelta(seconds=10))

        feature_proximity_analyzer_config.search_time_hours = 0
        feature_proximity_analyzer_config.save()

        analyzer = FeatureProximityAnalyzer(subject=subject_source.subject, config=feature_proximity_analyzer_config)

        result = analyzer.default_observations()

        # Burst extension picks up the 3 most recent + further obs in window
        # plus one prior. With 10s spacing and a 120s cutoff, all 5 obs are in
        # or just before the cutoff; we should see more than the 3-fix common
        # case.
        assert len(result) > 3
        assert len(result) <= FeatureProximityAnalyzer._HISTORY_FIXES

    def test_default_observations_burst_caps_at_history_fixes(self, subject_source, feature_proximity_analyzer_config):
        """Burst case with many obs in window: total result is capped at _HISTORY_FIXES."""
        # 30 obs spaced 5s apart — span 145s reaches past the 120s burst window
        # so we have plenty inside the burst plus prior fixes outside it.
        self._create_observations(subject_source.source, count=30, interval=timedelta(seconds=5))

        feature_proximity_analyzer_config.search_time_hours = 0
        feature_proximity_analyzer_config.save()

        analyzer = FeatureProximityAnalyzer(subject=subject_source.subject, config=feature_proximity_analyzer_config)

        result = analyzer.default_observations()

        assert len(result) == FeatureProximityAnalyzer._HISTORY_FIXES

    def test_default_observations_with_time_window_non_burst_returns_three(
        self, subject_source, feature_proximity_analyzer_config
    ):
        """search_time_hours > 0, non-burst case still returns 3 items."""
        self._create_observations(subject_source.source, count=5, interval=timedelta(minutes=1))

        feature_proximity_analyzer_config.search_time_hours = 24.0
        feature_proximity_analyzer_config.save()

        analyzer = FeatureProximityAnalyzer(subject=subject_source.subject, config=feature_proximity_analyzer_config)

        result = analyzer.default_observations()

        assert len(result) == 3
