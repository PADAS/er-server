import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import django_multitenant
import pytest
from django_fakeredis.fakeredis import get_fake_redis
from django_multitenant.utils import get_current_tenant, set_current_tenant
from factory import Faker
from oauth2_provider.models import get_application_model
from pytest_factoryboy import register

from django.apps import apps
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from rest_framework.test import APIClient

from accounts.utils import add_tenant_to_permission_codename
from core.models import DASTenant
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
from utils.tenant.managers import TenantContextManager

Application = get_application_model()
User = apps.get_model(app_label="accounts", model_name="User")

with open(Path(__file__).parent / "core/fixtures/tenant-response.json") as tenant_response:
    TENANT_RESPONSE = json.load(tenant_response)


class APIClientWithUser(APIClient):
    user: User = None


@pytest.fixture
def patrol():
    return PatrolFactory()


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
    return PatrolFactory.create_batch(5)


@pytest.fixture
def five_patrol_notes():
    return PatrolNoteFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment():
    return PatrolSegmentFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_subject():
    return PatrolSegmentSubjectFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_user():
    return PatrolSegmentUserFactory.create_batch(5)


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
        permission = PermissionFactory.create(name=name, content_type=content_type, codename=code_name)
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
    das_tenant = get_current_tenant()
    permission_codenames = [
        add_tenant_to_permission_codename(tenant_id=das_tenant.id, codename=codename) for codename in request.param
    ]
    permissions = Permission.objects.filter(codename__in=permission_codenames)
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
def superuser(das_tenant):
    return UserFactory(is_superuser=True, das_tenant=das_tenant)


@pytest.fixture
def user():
    return UserFactory(is_superuser=False)


@pytest.fixture
def superuser_client(application, superuser, tenant):
    with TenantContextManager(domain=tenant.domain):
        token = AccessTokenFactory(user=superuser, application=application).token
    client = APIClientWithUser()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    client.force_login(user=superuser)
    client.user = superuser
    return client


@pytest.fixture
def user_client(application, user, tenant):
    with TenantContextManager(domain=tenant.domain):
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
def das_tenant(tenant):
    return TenantFactory.create(id=tenant.id, domain=tenant.domain)


@pytest.fixture
def one_tenant():
    """Return a DASTenant and a matching tenant settings object"""

    tenant = TenantFactory(id=Faker("uuid4"), domain=Faker("hostname"))
    tenant_settings = copy.deepcopy(TENANT_RESPONSE)
    tenant_settings["domain"] = tenant.domain
    tenant_settings["id"] = tenant.id
    tenant_settings["slugName"] = Faker("slug")
    tenant_settings["name"] = Faker("company")
    tenant_settings["url"] = f"https://{tenant.domain}"
    tenant_settings = Tenant.from_dict(tenant_settings)

    return (tenant, tenant_settings)


@pytest.fixture()
def tenant_two(request, monkeypatch, one_tenant):
    """Return a DASTenant and a matching tenant settings object. Additionally the initial data has been loaded into the db for this tenant"""
    das_tenant = one_tenant[0]
    tenant_settings = one_tenant[1]

    previous_tenant = get_current_tenant()

    with monkeypatch.context() as m:
        set_current_tenant(das_tenant)
        thread = MagicMock()
        thread.tenant_object = tenant_settings
        m.setattr("utils.tenant.thread._get_local_thread", MagicMock(return_value=thread))

        call_command("loaddata_with_tenant", "initial_data")

    set_current_tenant(previous_tenant)

    if getattr(request, "cls", None):
        request.cls.tenant_two = one_tenant
        request.cls.tenant_two_settings = tenant_settings
        request.cls.tenant_two_object = das_tenant

    yield one_tenant


@pytest.fixture
def five_tenants():
    previous_tenant = get_current_tenant()
    set_current_tenant(None)

    yield TenantFactory.create_batch(size=5, id=Faker("uuid4"), domain=Faker("domain_name"))

    set_current_tenant(previous_tenant)


@pytest.fixture
def tenant_settings(request, monkeypatch, tenant):
    """This fixture is used to monkeypatch the get/set of tenant_settings on the current thread.
    Secondly if used as a class fixture, it injects the tenant settings into that class
    so that individual tests can access tenant_settings.
    For example self.tenant_settings.domain="test.com" """
    thread = MagicMock()
    thread.tenant_object = tenant
    monkeypatch.setattr("utils.tenant.thread._local_thread", thread)
    monkeypatch.setattr("utils.tenant.thread.set_tenant_settings", MagicMock(return_value=None))
    monkeypatch.setattr("utils.tenant.thread.clear_tenant_settings", MagicMock(return_value=None))
    if getattr(request, "cls", None):
        request.cls.tenant_settings = tenant
    return tenant


@pytest.fixture
def das_tenant_monkeypatch(request, monkeypatch, das_tenant):
    """This fixture is used to monkeypatch the get/set of das_tenant on the current thread.
    Secondly if used as a class fixture, it injects the das_tenant into that class
    so that individual tests can access the das_tenant object.
    For example self.das_tenant.id"""
    thread_locals = MagicMock()
    thread_locals.tenant = das_tenant
    monkeypatch.setattr(django_multitenant.utils, "_thread_locals", thread_locals)
    monkeypatch.setattr("django_multitenant.utils.set_current_tenant", MagicMock(return_value=None))
    monkeypatch.setattr("django_multitenant.utils.unset_current_tenant", MagicMock(return_value=None))
    if getattr(request, "cls", None):
        request.cls.das_tenant = das_tenant
    return das_tenant


@pytest.fixture(autouse=True, scope="session")
def tenant_post_db_setup(django_db_setup, django_db_blocker):
    """This session-scoped fixture creates the primary unit test tenant in the database."""
    with django_db_blocker.unblock():
        DASTenant.objects.get_or_create(id=TENANT_RESPONSE["id"], defaults=dict(domain=TENANT_RESPONSE["domain"]))


@pytest.fixture
def multitenant_cache_client(monkeypatch):
    redis_module = MagicMock()
    cache_client = get_fake_redis()
    redis_module.from_url.return_value = cache_client
    monkeypatch.setattr("utils.tenant.cache.redis", redis_module)

    return cache_client


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
