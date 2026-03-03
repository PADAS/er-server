import json
import logging
import os
import urllib
from datetime import timedelta

import pytest
import yaml
from django_multitenant.utils import set_current_tenant

from django.contrib.gis.geos import LineString, Point, Polygon
from django.core.files import File
from django.core.serializers import serialize
from django.test import TestCase, override_settings
from django.utils import timezone

from activity.models import Event, EventCategory, EventType
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.geofence import GeofenceAnalyzer, GeofenceAnalyzerConfig
from analyzers.models import SubjectAnalyzerResult
from analyzers.tasks import analyze_subject_
from core.utils import DASTenantManagement
from mapping.models import (
    SpatialFeature,
    SpatialFeatureFile,
    SpatialFeatureGroupStatic,
    SpatialFeatureType,
)
from mapping.spatialfile_utils import process_spatialfile
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

from .analyzer_test_utils import (
    generate_observations,
    parse_recorded_at,
    store_observations,
    time_shift,
)
from .geofence_test_data import (
    CORNER_CLIPPING_TRACK,
    DUMBO_TRACKS,
    JOLIE_TRACK,
    OLCHODA_TRACK,
    SUBJECT_TRACK_FOR_DOUBLE_FENCE_HOP,
    TUMBO_TRACKS,
    ZERO_CROSSINGS,
)

logger = logging.getLogger(__name__)

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")

das_tenant_management = DASTenantManagement(domain="domain.com")


@override_settings(DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage")
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGeofenceAnalyzer(TestCase):
    @classmethod
    def event_schema_json(cls):
        schema_yaml = """
            schema:
              $schema: http://json-schema.org/draft-04/schema#
              definition:
              - name
              - details
              - geofence_name
              - contain_regions
              - subject_speed_kmhr
              - subject_heading
              - total_fix_count
              properties:
                name:
                  title: Name of subject
                  type: string
                details:
                  title: Details
                  type: string
                geofence_name:
                  title: Geofence Name
                  type: string
                contain_regions:
                  title: Current Region
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
              title: EventType Geofencing
              type: object
            """
        return json.dumps(yaml.load(schema_yaml, Loader=yaml.SafeLoader))

    def feature_from_observation_list(
        self, observations, name="Subject Track", stroke="#cc0000", stroke_width=3, stroke_opacity=1
    ):
        """Create a generic LineString feature from a list of Observations."""
        feature = {
            "type": "Feature",
            "properties": {
                "name": name,
                "stroke": stroke,
                "stroke-width": stroke_width,
                "stroke-opacity": stroke_opacity,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [(obs.location.x, obs.location.y) for obs in observations],
            },
        }

        return feature

    def visualize_geofence_crossings(self, geofence_grp, track_observations, subject, filename):
        if logger.isEnabledFor(logging.DEBUG):
            # Write results to a local file.
            fences = json.loads(
                serialize(
                    "geojson", geofence_grp.features.all(), geometry_field="feature_geometry", fields=("name", "id")
                )
            )
            fences["features"] = fences["features"] + [self.feature_from_observation_list(track_observations)]

            fence_breaks = json.loads(
                serialize(
                    "geojson",
                    SubjectAnalyzerResult.objects.filter(subject=subject),
                    geometry_field="geometry_collection",
                    fields=("title", "estimated_time"),
                )
            )

            fences["features"] = fences["features"] + fence_breaks["features"]

            with open(f"{filename}.json", "w") as fo:
                json.dump(fences, fo, indent=2)

            # Print a link to view results at geojson.io
            data = urllib.parse.quote(json.dumps(fences))
            logger.info(f"http://geojson.io/#data=data:application/json,{data}")

    def setUp(self):
        set_current_tenant(self.das_tenant)

        data = File(open(os.path.join(FIXTURE_PATH, "lines.geojson"), "rb"))
        feature_types_file = File(open(os.path.join(FIXTURE_PATH, "spatial_feature_types.geojson"), "rb"))
        spatialfile = SpatialFeatureFile.objects.create(data=data, feature_types_file=feature_types_file)
        process_spatialfile(spatialfile)

        data = File(open(os.path.join(FIXTURE_PATH, "polygons.geojson"), "rb"))
        feature_types_file = File(open(os.path.join(FIXTURE_PATH, "spatial_feature_types.geojson"), "rb"))
        spatialfile = SpatialFeatureFile.objects.create(data=data, feature_types_file=feature_types_file)
        process_spatialfile(spatialfile)

        ec, created = EventCategory.objects.get_or_create(
            value="analyzer_event", defaults=dict(display="Analyzer Events")
        )

        EventType.objects.get_or_create(
            value="geofence_break",
            category=ec,
            defaults=dict(display="Geofence Analyzer", schema=self.event_schema_json()),
        )

    def test_geofencing_integration(self):
        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(name="Jolie", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="006")
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id="elephant", speed_KmHr=7.0)

        sg = SubjectGroup.objects.create(
            name="geofence_subject_analyzer_group1",
        )
        sg.subjects.add(sub)
        sg.save()

        # Create a SpatialFeatureGroupStatic group with the 'Moukabala-Doudou'
        # geofence
        geofences = SpatialFeature.objects.filter(name__iexact="Moukalaba-Doudou")
        logger.info("Geofence count: %s" % len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name="Gabon Geofences",
        )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        test_observations = [parse_recorded_at(x) for x in JOLIE_TRACK]
        test_observations = list(time_shift(test_observations))

        # Create the Geofence Analyzer Config object
        GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp, search_time_hours=24.0, trigger_on_corner_clip=False
        )

        for idx in range(0, len(test_observations) - 2):
            # Store the entire list of observations.
            store_observations(test_observations[idx : idx + 1], timeshift=False, source=source)
            analyze_subject_(str(sub.id))

        results = SubjectAnalyzerResult.objects.filter(subject=sub)

        for result in results:
            logger.info(f"Geofence Result: {result}")

        self.assertEqual(len(results), 1)

        for e in Event.objects.all():
            for ed in e.event_details.all():
                assert ed.data["event_details"]["feature_group_name"] == gf_grp.name

    def test_geofencing_logic(self):
        """Test functioning of the geofence algorithm logic"""

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(name="Olchoda", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="007")
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name="geofence_subject_analyzer_group2",
        )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in OLCHODA_TRACK]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(name__iexact="Ol Donyo Farm 2")
        logger.info("Geofence count: %s", len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name="Mara Geofences",
        )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_region_name = "Pardamat Conservancy"
        contain_rgns = SpatialFeature.objects.filter(name=contain_region_name)
        logger.info("Containment region count: %s" % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name="Geofence Containment Regions",
        )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp, containment_regions=cr_grp
        )

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len + 1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2 : i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        self.assertTrue(len(results) == 2)
        for result in results:
            logger.info("Geofence Result: %s" % result)

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())
            assert e.event_details.all().first().data["event_details"]["contain_regions"] == "Pardamat Conservancy"

        for e in Event.objects.all():
            for ed in e.event_details.all():
                logger.info("Event Details: %s" % ed.data)

    def test_geofencing_for_crooked_boundaries(self):
        sub = Subject.objects.create(name="dumbo", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="007")
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name="geofence_subject_analyzer_group2",
        )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in DUMBO_TRACKS]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(name__iexact="Ol Donyo Farm 2")
        logger.info("Geofence count: %s", len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name="Crooked Geofences",
        )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(name="Pardamat Conservancy")
        logger.info("Containment region count: %s" % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name="Geofence Containment Regions",
        )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp, containment_regions=cr_grp, trigger_on_corner_clip=False
        )

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len + 1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2 : i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        for result in results:
            logger.info("Geofence Result: %s" % result)

        self.assertEqual(len(results), 6)

        self.visualize_geofence_crossings(
            gf_grp, test_observations, sub, self.test_geofencing_for_crooked_boundaries.__name__
        )

    def test_geofencing_for_a_double_hop(self):
        sub = Subject.objects.create(name="dumbo", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="007")
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name="geofence_subject_analyzer_group2",
        )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in SUBJECT_TRACK_FOR_DOUBLE_FENCE_HOP]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(name__iexact="Ol Donyo Farm 2")
        logger.info("Geofence count: %s", len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name="Crooked Geofences",
        )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(name="Pardamat Conservancy")
        logger.info("Containment region count: %s" % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name="Geofence Containment Regions",
        )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp, containment_regions=cr_grp, trigger_on_corner_clip=False
        )

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len + 1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2 : i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        for result in results:
            logger.info("Geofence Result: %s" % result)
            assert result.values["contain_regions"] == "Pardamat Conservancy"

        self.assertEqual(len(results), 1)

        self.visualize_geofence_crossings(
            gf_grp, test_observations, sub, self.test_geofencing_for_a_double_hop.__name__
        )

    def test_illegitimate_fence_crossings(self):
        sub = Subject.objects.create(name="dumbo", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="007")
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name="geofence_subject_analyzer_group2",
        )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in TUMBO_TRACKS]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(name__iexact="Ol Donyo Farm 2")
        logger.info("Geofence count: %s", len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name="Crooked Geofences",
        )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(name="Ol Donyo Farm 2")
        logger.info("Containment region count: %s" % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name="Geofence Containment Regions",
        )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp, containment_regions=cr_grp, trigger_on_corner_clip=False
        )

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len + 1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2 : i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        for result in results:
            logger.info("Geofence Result: %s" % result)

        self.assertEqual(len(results), 0)

        self.visualize_geofence_crossings(
            gf_grp, test_observations, sub, self.test_illegitimate_fence_crossings.__name__
        )

    def test_zero_crossings(self):
        sub = Subject.objects.create(name="dumbo", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="007")
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name="geofence_subject_analyzer_group2",
        )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in ZERO_CROSSINGS]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(name__iexact="Ol Donyo Farm 2")
        logger.info("Geofence count: %s", len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name="Crooked Geofences",
        )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(name="Ol Donyo Farm 2")
        logger.info("Containment region count: %s" % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name="Geofence Containment Regions",
        )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp, containment_regions=cr_grp, trigger_on_corner_clip=False
        )

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len + 1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2 : i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        for result in results:
            logger.info("Geofence Result: %s" % result)

        self.assertEqual(len(results), 0)

        self.visualize_geofence_crossings(gf_grp, test_observations, sub, self.test_zero_crossings.__name__)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestGeofenceAnalyzerQuietPeriod:
    OBSERVATIONS = [
        {
            "longitude": 3.538229,
            "latitude": 10.005134,
            "recorded_at": "2021-10-09T23:00:13+00:00",
        },
        {
            "longitude": 3.535698,
            "latitude": 10.025114,
            "recorded_at": "2021-10-09T23:30:20+00:00",
        },
        {
            "longitude": 3.523348,
            "latitude": 10.009393,
            "recorded_at": "2021-10-10T00:00:24+00:00",
        },
        {
            "longitude": 3.526284,
            "latitude": 10.021463,
            "recorded_at": "2021-10-10T00:30:31+00:00",
        },
        {
            "longitude": 3.510491,
            "latitude": 10.018116,
            "recorded_at": "2021-10-10T01:00:31+00:00",
        },
    ]

    def _setup_geofence_test(
        self,
        subject_source,
        spatial_feature_type,
        spatial_feature_group_static,
        geofence_analyzer_config,
        dummy_cache,
        event_type,
        caplog,
        monkeypatch,
    ):

        wildlife_subject_type = SubjectType.objects.get(value="wildlife")
        elephant_subject_subtype = SubjectSubType.objects.get(value="elephant")
        elephant_subject_subtype.subject_type = wildlife_subject_type
        elephant_subject_subtype.save()

        subject_source.subject.subject_subtype = elephant_subject_subtype
        subject_source.subject.save()

        subject = subject_source.subject

        subject_group = geofence_analyzer_config.subject_group
        subject_group.name = "geofence_subject_analyzer_group1"
        subject_group.save()
        subject_group.subjects.add(subject)

        spatial_feature = SpatialFeature.objects.create(
            feature_type=spatial_feature_type,
            feature_geometry=LineString(Point(3.543898, 10.009698), Point(3.505531, 10.028968)),
        )
        spatial_feature_group_static.features.add(spatial_feature)

        geofence_analyzer_config.quiet_period = timedelta(0, 9000)
        geofence_analyzer_config.critical_geofence_group = spatial_feature_group_static
        geofence_analyzer_config.subject_group = subject_group
        geofence_analyzer_config.save()

        event_type.value = "geofence_break"
        event_type.save()

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

    def test_geofence_quiet_period(
        self,
        subject_source,
        spatial_feature_type,
        spatial_feature_group_static,
        geofence_analyzer_config,
        dummy_cache,
        event_type,
        caplog,
        monkeypatch,
        das_tenant_monkeypatch,
    ):
        set_current_tenant(das_tenant_monkeypatch)
        caplog.set_level(logging.INFO)

        self._setup_geofence_test(
            subject_source,
            spatial_feature_type,
            spatial_feature_group_static,
            geofence_analyzer_config,
            dummy_cache,
            event_type,
            caplog,
            monkeypatch,
        )

        assert f"Pausing analyzer with id={geofence_analyzer_config.id}" in caplog.text
        assert f"The analyzer {geofence_analyzer_config.id} is quiet for a while" not in caplog.text
        assert Event.objects.all().count() == 4
        assert Event.objects.all()[0].event_type.value == "geofence_break"

    def test_geofence_quiet_period_check_analyzer_is_paused(
        self,
        subject_source,
        spatial_feature_type,
        spatial_feature_group_static,
        geofence_analyzer_config,
        dummy_cache,
        event_type,
        caplog,
        monkeypatch,
    ):

        caplog.set_level(logging.INFO)
        self._setup_geofence_test(
            subject_source,
            spatial_feature_type,
            spatial_feature_group_static,
            geofence_analyzer_config,
            dummy_cache,
            event_type,
            caplog,
            monkeypatch,
        )

        analyze_subject_(subject_source.subject.id)
        analyze_subject_(subject_source.subject.id)

        assert f"Pausing analyzer with id={geofence_analyzer_config.id}" in caplog.text
        assert f"The analyzer {geofence_analyzer_config.id} is quiet for a while" in caplog.text
        assert Event.objects.all().count() == 4

    def test_geofence_event_details_rounding(
        self,
        subject_source,
        spatial_feature_type,
        spatial_feature_group_static,
        geofence_analyzer_config,
        dummy_cache,
        event_type,
        caplog,
        monkeypatch,
    ):

        caplog.set_level(logging.INFO)
        self._setup_geofence_test(
            subject_source,
            spatial_feature_type,
            spatial_feature_group_static,
            geofence_analyzer_config,
            dummy_cache,
            event_type,
            caplog,
            monkeypatch,
        )

        analyze_subject_(subject_source.subject.id)
        assert Event.objects.all().count() == 4

        speed = Event.objects.all()[0].event_details.first().data.get("event_details", {}).get("subject_speed_kmhr")
        assert speed == round(speed, 2)


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestCornerClipping(TestCase):
    """Test corner clipping functionality with trigger_on_corner_clip field"""

    def setUp(self):
        set_current_tenant(self.das_tenant)

        ec, created = EventCategory.objects.get_or_create(
            value="analyzer_event", defaults=dict(display="Analyzer Events")
        )

        EventType.objects.get_or_create(
            value="geofence_break",
            category=ec,
            defaults=dict(display="Geofence Analyzer", schema=TestGeofenceAnalyzer.event_schema_json()),
        )

        # Create models (Subject, SubjectSource and Source)
        self.subject = Subject.objects.create(name="corner_test_subject", subject_subtype_id="elephant")
        source = Source.objects.create(manufacturer_id="008")
        SubjectSource.objects.create(subject=self.subject, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        self.subject_group = SubjectGroup.objects.create(name="corner_clipping_group_false")
        self.subject_group.subjects.add(self.subject)
        self.subject_group.save()

        # Create a rectangular geofence from lat -1.0 to -0.9, lon 34.9 to 35.1
        geofence_geom = LineString([(34.9, -1.0), (35.1, -1.0), (35.1, -0.9), (34.9, -0.9), (34.9, -1.0)])
        spatial_feature_type = SpatialFeatureType.objects.get_or_create(name="test_geofence")[0]
        gf = SpatialFeature.objects.create(
            name="Corner Clip Test Fence",
            feature_geometry=geofence_geom,
            feature_type=spatial_feature_type,
        )
        self.spatial_feature_group = SpatialFeatureGroupStatic.objects.create(name="Corner Clip Fences")
        self.spatial_feature_group.features.add(gf)
        self.spatial_feature_group.save()

    def test_corner_clipping_disabled(self):
        """Test that corner clipping events are NOT triggered when trigger_on_corner_clip=False"""

        # Create analyzer config with trigger_on_corner_clip=False
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=self.subject_group,
            critical_geofence_group=self.spatial_feature_group,
            trigger_on_corner_clip=False,
        )

        # Parse and generate observations for corner clipping track
        test_observations = [parse_recorded_at(x) for x in CORNER_CLIPPING_TRACK]
        test_observations = list(generate_observations(test_observations))

        # Run analysis
        analyzer = GeofenceAnalyzer(config=config, subject=self.subject)
        analyzer.analyze(observations=test_observations)

        # Should have NO results since corner clipping is disabled
        results = SubjectAnalyzerResult.objects.filter(subject=self.subject)
        assert len(results) == 0, f"Expected 0 results with corner clipping disabled, got {len(results)}"

    def _test_corner_clipping(self):
        """Test that corner clipping events ARE triggered when trigger_on_corner_clip=True"""

        # Create analyzer config with trigger_on_corner_clip=True
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=self.subject_group,
            critical_geofence_group=self.spatial_feature_group,
            trigger_on_corner_clip=True,
        )

        # Parse and generate observations for corner clipping track
        test_observations = [parse_recorded_at(x) for x in CORNER_CLIPPING_TRACK]
        test_observations = list(generate_observations(test_observations))

        # Run analysis
        analyzer = GeofenceAnalyzer(config=config, subject=self.subject)
        results = analyzer.analyze(observations=test_observations)

        # Should have two results since corner clipping is enabled
        assert len(results) == 2, f"Expected 2 results with corner clipping enabled, got {len(results)}"

        # Verify the results contain expected geofence crossing locations
        assert results[0][1].location.coords == (35.1, -0.95)
        assert results[1][1].location.coords == (34.9, -0.95)

    def test_corner_clipping_enabled_line_geofence(self):
        self._test_corner_clipping()

    def test_corner_clipping_enabled_polygon_geofence(self):
        geofence_geom = Polygon([(34.9, -1.0), (35.1, -1.0), (35.1, -0.9), (34.9, -0.9), (34.9, -1.0)])
        spatial_feature_type = SpatialFeatureType.objects.get_or_create(name="test_polygon_geofence")[0]
        gf = SpatialFeature.objects.create(
            name="Polygon Test Fence",
            feature_geometry=geofence_geom,
            feature_type=spatial_feature_type,
        )
        self.spatial_feature_group = SpatialFeatureGroupStatic.objects.create(name="Polygon Fences")
        self.spatial_feature_group.features.add(gf)
        self.spatial_feature_group.save()

        self._test_corner_clipping()
