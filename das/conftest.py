import pytest

from factories import (
    PatrolFactory,
    PatrolNoteFactory,
    PatrolSegmentFactory,
    PatrolSegmentSubjectFactory,
    PatrolSegmentUserFactory,
    SubjectSourceFactory,
    GeofenceAnalyzerConfigFactory,
    SpatialFeatureGroupStaticFactory,
    SpatialFeatureTypeFactory,
    EventTypeFactory,
    FeatureProximityAnalyzerConfigFactory,
)


@pytest.fixture
def patrol():
    PatrolFactory()


@pytest.fixture
def five_patrols():
    PatrolFactory.create_batch(5)


@pytest.fixture
def five_patrol_notes():
    PatrolNoteFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment():
    PatrolSegmentFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_subject():
    PatrolSegmentSubjectFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_user():
    PatrolSegmentUserFactory.create_batch(5)


@pytest.fixture
def subject_source():
    return SubjectSourceFactory.create()


@pytest.fixture
def geofence_analyzer_config():
    return GeofenceAnalyzerConfigFactory.create()


@pytest.fixture
def feature_proximity_analyzer_config():
    return FeatureProximityAnalyzerConfigFactory.create()


@pytest.fixture
def spatial_feature_group_static():
    return SpatialFeatureGroupStaticFactory.create()


@pytest.fixture
def spatial_feature_type():
    return SpatialFeatureTypeFactory.create()


@pytest.fixture
def event_type():
    return EventTypeFactory.create()


@pytest.fixture(autouse=True)
def dummy_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
