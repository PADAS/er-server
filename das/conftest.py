import json
from unittest.mock import MagicMock

import pytest
from oauth2_provider.models import get_application_model
from pytest_factoryboy import register

from django.apps import apps
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from factories import (
    AccessTokenFactory,
    ChoiceFactory,
    CommunityFactory,
    EventCategoryFactory,
    EventDetailsFactory,
    EventFactory,
    EventGeometryFactory,
    EventNoteFactory,
    EventTypeFactory,
    FeatureProximityAnalyzerConfigFactory,
    GeofenceAnalyzerConfigFactory,
    ObservationFactory,
    PatrolFactory,
    PatrolNoteFactory,
    PatrolSegmentFactory,
    PatrolSegmentSubjectFactory,
    PatrolSegmentUserFactory,
    PermissionFactory,
    PermissionSetFactory,
    ProviderFactory,
    SourceFactory,
    SourceGroupFactory,
    SpatialFeatureGroupStaticFactory,
    SpatialFeatureTypeFactory,
    SubjectFactory,
    SubjectGroupFactory,
    SubjectSourceFactory,
    SubjectSubTypeFactory,
    TenantFactory,
    UserFactory,
)
from utils.features import features
from utils.tenant import Tenant
from utils.tenant.thread import clear_tenant_settings, set_tenant_settings

Application = get_application_model()
User = apps.get_model(app_label="accounts", model_name="User")

TENANT_RESPONSE = {
    "id": "c0973be2-8e11-4cb8-8463-897fb96391d0",
    "createdAt": "2022-11-14T21:09:02.519164+00:00",
    "updatedAt": "2022-11-14T21:09:02.519165+00:00",
    "name": "Frank test1",
    "slugName": "frank-test1",
    "url": "http://zoo.com",
    "domain": "zoo.com",
    "status": "PROVISIONING",
    "envSettings": {
        "acceptEula": False,
        "alertRateLimit": 40,
        "allServerNames": None,
        "defaultEventFilterFromDays": None,
        "defaultPatrolFilterFromDays": None,
        "eusOrg": None,
        "fqdn": "http://zoo.com",
        "geoPermissionSpeedKmH": 75,
        "geoPermissionRadiusMeters": 3704,
        "geoPermissionViolationBanDurationMin": 10,
        "gsBucketName": None,
        "kmlOverlayImage": None,
        "kmlFeedTitle": "EarthRanger KML service",
        "patrolEnabled": False,
        "showStationarySubjectsOnMap": True,
        "showTrackDays": 16,
        "subjectRegionEnabled": False,
        "tableauDefaultDashboard": False,
        "tableauSiteId": False,
        "trackLength": False,
    },
    "featureFlags": {
        "alertsEnabled": False,
        "dailyReportEnabled": False,
        "kmlExport": False,
        "mappingFeaturesV2": True,
        "tableauEnabled": False,
        "tableauSiteId": False,
        "trackLength": False,
    },
    "services": {
        "auth": {"status": "PROVISIONING", "statusMessage": None, "updatedAt": ""},
        "media": {"status": "PROVISIONING", "statusMessage": None, "updatedAt": ""},
    },
}


class APIClientWithUser(APIClient):
    user: User = None


@pytest.fixture
def patrol():
    PatrolFactory()


@pytest.fixture
def subject():
    return SubjectFactory()


@pytest.fixture
def subject_subtype():
    return SubjectSubTypeFactory()


@pytest.fixture
def source():
    return SourceFactory()


@pytest.fixture
def five_sources():
    return SourceFactory.create_batch(5)


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
    return PatrolSegmentSubjectFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_user():
    PatrolSegmentUserFactory.create_batch(5)


@pytest.fixture
def five_subjects():
    return SubjectFactory.create_batch(5)


register(UserFactory, "ops_user")


@pytest.fixture
def view_subject_permissions():
    return [
        Permission.objects.get_by_natural_key("view_subjectgroup", "observations", "subjectgroup"),
        Permission.objects.get_by_natural_key("view_subject", "observations", "subject"),
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
    view_sg_a_permissionset = PermissionSetFactory.create(permissions=view_subject_permissions)
    view_sg_b_permissionset = PermissionSetFactory.create(permissions=view_subject_permissions)
    return [
        SubjectGroupFactory.create(permission_sets=[view_sg_a_permissionset], subjects=SubjectFactory.create_batch(2)),
        SubjectGroupFactory.create(permission_sets=[view_sg_b_permissionset], subjects=SubjectFactory.create_batch(2)),
    ]


@pytest.fixture
def patrol_configuration(two_subject_groups):
    PatrolConfiguration = apps.get_model(app_label="activity", model_name="PatrolConfiguration")
    configuration = PatrolConfiguration.objects.first()

    for subject_group in two_subject_groups:
        configuration.subject_groups.add(subject_group)

    return configuration


@pytest.fixture
def view_subjects_permission_set(view_subject_permissions):
    return PermissionSetFactory.create(permissions=view_subject_permissions)


@pytest.fixture()
def subject_group_with_perms(request):
    permissions = []
    for permission in request.param:
        permission = permission.split(",")
        try:
            codename, app_label, model = permission[0], permission[1], permission[2]
            permission = Permission.objects.get_by_natural_key(codename, app_label, model)
            permissions.append(permission)
        except Permission.DoesNotExist:
            print(f"Does not exits a permission with the next params {permission}")
    return SubjectGroupFactory.create(permission_sets=[PermissionSetFactory.create(permissions=permissions)])


@pytest.fixture
def permission_set_with_permissions(request):
    permission_set = PermissionSetFactory()
    for permission in request.param:
        name, app_label, model, code_name = permission
        content_type = ContentType.objects.get(app_label=app_label, model=model)
        permission = PermissionFactory.create(name=name, content_type=content_type, code_name=code_name)
        permission_set.permissions.add(permission)
    return permission_set


@pytest.fixture
def subject_group_without_permissions():
    return SubjectGroupFactory.create()


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


@pytest.fixture
def five_event_types():
    return EventTypeFactory.create_batch(5)


@pytest.fixture(autouse=True)
def dummy_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }


@pytest.fixture
def five_events():
    return EventFactory.create_batch(5)


@pytest.fixture
def event_with_detail():
    return EventDetailsFactory()


@pytest.fixture
def five_events_with_details():
    return EventDetailsFactory.create_batch(5)


@pytest.fixture
def five_event_notes():
    return EventNoteFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_user_with_leader_uuid():
    for i in range(1, 6):
        PatrolSegmentSubjectFactory.create(leader__id=f"00000000-0000-0000-0000-00000000000{i}")


@pytest.fixture
def five_patrol_segment_patrol_type_uuid():
    for i in range(1, 6):
        PatrolSegmentFactory.create(patrol_type__id=f"00000000-0000-0000-0000-00000000000{i}")


@pytest.fixture
def source_provider():
    return ProviderFactory.create()


@pytest.fixture
def events_with_category(request):
    return [
        EventFactory.create(title=f"Title {category}", event_type__category__value=category)
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


@pytest.fixture
def application():
    application, _ = Application.objects.get_or_create(client_id="das_web_client")
    return application


@pytest.fixture
def superuser():
    tenant = TenantFactory(domain="localhost")
    return UserFactory(is_superuser=True, das_tenant=tenant)


@pytest.fixture
def user():
    return UserFactory(is_superuser=False)


@pytest.fixture
def superuser_client(application, superuser):
    token = AccessTokenFactory(user=superuser, application=application).token
    client = APIClientWithUser()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    client.force_login(user=superuser)
    client.user = superuser
    return client


@pytest.fixture
def user_client(application, user):
    token = AccessTokenFactory(user=user, application=application).token
    client = APIClientWithUser()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    client.force_login(user=user)
    client.user = user
    return client


@pytest.fixture
def event_geometry_with_polygon():
    return EventGeometryFactory.create(event__event_type__geometry_type="Polygon")


@pytest.fixture
def five_event_geometries():
    return EventGeometryFactory.create_batch(5)


@pytest.fixture
def observation():
    return ObservationFactory()


@pytest.fixture
def five_observations():
    return ObservationFactory.create_batch(5)


@pytest.fixture
def tenant_response():
    return TENANT_RESPONSE


@pytest.fixture
def tenant_thread(tenant_response):
    set_tenant_settings(tenant_response)
    yield None
    clear_tenant_settings()


@pytest.fixture
def feature_tms(monkeypatch):
    feature_tms_mock = MagicMock()
    feature_tms_mock.is_on.return_value = True
    monkeypatch.setitem(features._features, "tms", feature_tms_mock)
    return feature_tms_mock


@pytest.fixture
def memory_store_client_mock(monkeypatch, tenant_response):
    memory_store_client_mock = MagicMock()
    memory_store_client_mock.get_key.return_value = json.dumps(tenant_response)
    monkeypatch.setattr("utils.tenant.providers.memory_store_client", memory_store_client_mock)
    return memory_store_client_mock


@pytest.fixture
def tms_api_client_mock(monkeypatch, tenant_response):
    tms_client_mock = MagicMock()
    monkeypatch.setattr("utils.tenant.providers.tms_api_client", tms_client_mock)
    return tms_client_mock


@pytest.fixture
def tenant(tenant_response):
    return Tenant.from_dict(tenant_response)


@pytest.fixture
def tenant_settings(monkeypatch, tenant):
    thread = MagicMock()
    thread.tenant_object = tenant
    monkeypatch.setattr("utils.tenant.thread._get_main_thread", MagicMock(return_value=thread))

    return tenant


@pytest.fixture(scope="function")
def tenant_response_for_test_case(request, tenant):
    request.cls.tenant_response = tenant


@pytest.fixture
def choice():
    return ChoiceFactory.create()


@pytest.fixture
def five_choices():
    return ChoiceFactory.create_batch(5)


@pytest.fixture
def five_users():
    return UserFactory.create_batch(5)


@pytest.fixture
def community():
    return CommunityFactory()


@pytest.fixture
def five_communities():
    return CommunityFactory.build_batch(5)


@pytest.fixture
def source_group():
    return SourceGroupFactory()
