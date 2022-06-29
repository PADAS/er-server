import pytest
from pytest_factoryboy import register

from django.contrib.auth.models import Permission

from factories import (EventCategoryFactory, EventDetailsFactory, EventFactory,
                       EventTypeFactory, FeatureProximityAnalyzerConfigFactory,
                       GeofenceAnalyzerConfigFactory, PatrolFactory,
                       PatrolNoteFactory, PatrolSegmentFactory,
                       PatrolSegmentSubjectFactory, PatrolSegmentUserFactory,
                       PermissionSetFactory, ProviderFactory, SourceFactory,
                       SpatialFeatureGroupStaticFactory,
                       SpatialFeatureTypeFactory, SubjectFactory,
                       SubjectGroupFactory, SubjectSourceFactory, UserFactory)


@pytest.fixture
def patrol():
    PatrolFactory()


@pytest.fixture
def subject():
    return SubjectFactory()


@pytest.fixture
def source():
    return SourceFactory()


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
def five_subjects():
    SubjectFactory.create_batch(5)


register(UserFactory, "ops_user")


@pytest.fixture
def view_subject_permissions():
    return [
        Permission.objects.get_by_natural_key(
            "view_subjectgroup", "observations", "subjectgroup"
        ),
        Permission.objects.get_by_natural_key(
            "view_subject", "observations", "subject"
        ),
    ]


@pytest.fixture
def subject_group_tree():
    """
    Tamed
     |- Dogs
    """
    root = SubjectGroupFactory(name="Tamed")
    root.children.add(SubjectGroupFactory(name="Dogs"))
    return root


@pytest.fixture
def subject_group_empty():
    return SubjectGroupFactory.create()


@pytest.fixture
def two_subject_groups(view_subject_permissions):
    view_sg_a_permissionset = PermissionSetFactory.create(
        permissions=view_subject_permissions)
    view_sg_b_permissionset = PermissionSetFactory.create(
        permissions=view_subject_permissions)
    return [
        SubjectGroupFactory.create(permission_sets=[
            view_sg_a_permissionset], subjects=SubjectFactory.create_batch(2)),
        SubjectGroupFactory.create(permission_sets=[view_sg_b_permissionset], subjects=SubjectFactory.create_batch(2))]


@pytest.fixture
def view_subjects_permission_set(view_subject_permissions):
    return PermissionSetFactory.create(permissions=view_subject_permissions)


@pytest.fixture()
def subject_group(request):
    permissions = []
    for permission in request.param:
        permission = permission.split(",")
        try:
            codename, app_label, model = permission[0], permission[1], permission[2]
            permission = Permission.objects.get_by_natural_key(
                codename, app_label, model
            )
            permissions.append(permission)
        except Permission.DoesNotExist:
            print(
                f"Does not exits a permission with the next params {permission}")
    return SubjectGroupFactory.create(permission_sets=[PermissionSetFactory.create(permissions=permissions)])


@pytest.fixture
def subject_source():
    return SubjectSourceFactory.create()


@pytest.fixture
def five_subject_sources():
    return SubjectSourceFactory.create_batch(5)


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


@pytest.fixture
def five_events():
    EventFactory.create_batch(5)


@pytest.fixture
def five_events_with_details():
    EventDetailsFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_user_with_leader_uuid():
    for i in range(1, 6):
        PatrolSegmentSubjectFactory.create(
            leader__id=f"00000000-0000-0000-0000-00000000000{i}"
        )


@pytest.fixture
def five_patrol_segment_patrol_type_uuid():
    for i in range(1, 6):
        PatrolSegmentFactory.create(
            patrol_type__id=f"00000000-0000-0000-0000-00000000000{i}"
        )


@pytest.fixture
def source_provider():
    return ProviderFactory.create()


@pytest.fixture
def events_with_category(request):
    return [
        EventFactory.create(
            title=f"Title {category}", event_type__category__value=category
        )
        for category in request.param
    ]


@pytest.fixture
def get_geo_permission_set(request):
    permissions = Permission.objects.filter(codename__in=request.param)
    return PermissionSetFactory.create(name="Test Geo Permissions - View", permissions=permissions)


@pytest.fixture
def basic_event_categories():
    categories = ["analyzer_event", "logistics", "monitoring", "security"]
    for category in categories:
        EventCategoryFactory.create(value=category)
