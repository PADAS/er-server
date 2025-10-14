import copy
import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Optional, Type
from unittest.mock import MagicMock

import django_multitenant
import pytest
from django_fakeredis.fakeredis import get_fake_redis
from django_multitenant.utils import get_current_tenant, set_current_tenant
from factory import Faker
from oauth2_provider.models import get_application_model
from pytest_factoryboy import register

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.urls import include, path
from django.utils import timezone
from django.views import View
from rest_framework.test import APIClient

from accounts.utils import add_tenant_to_permission_codename
from buoy.tests import generate_devices
from core.models import DASTenant
from factories import (
    AccessTokenFactory,
    ChoiceFactory,
    CommunityFactory,
    DisplayCategoryFactory,
    EventCategoryFactory,
    EventDetailsFactory,
    EventFactory,
    EventGeometryFactory,
    EventNoteFactory,
    EventTypeFactory,
    FeatureProximityAnalyzerConfigFactory,
    GearFactory,
    GeofenceAnalyzerConfigFactory,
    ObservationFactory,
    PatrolFactory,
    PatrolNoteFactory,
    PatrolSegmentFactory,
    PatrolSegmentSubjectFactory,
    PatrolSegmentUserFactory,
    PatrolTypeFactory,
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
    SubjectTypeFactory,
    TenantFactory,
    TwoWayMessageSubjectFactory,
    UserFactory,
)
from observations.models import Observation, SubjectStatus, SubjectSubType
from utils.features import features
from utils.tenant import Tenant
from utils.tenant.managers import TenantContextManager

Application = get_application_model()
User = apps.get_model(app_label="accounts", model_name="User")

with open(Path(__file__).parent / "core/fixtures/tenant-response.json") as tenant_response_body:
    TENANT_RESPONSE = json.load(tenant_response_body)


class APIClientWithUser(APIClient):
    user: User = None


@pytest.fixture
def anonymous_client():
    return APIClient()


@pytest.fixture
def patrol():
    return PatrolFactory()


@pytest.fixture
def subject():
    return SubjectFactory()


@pytest.fixture
def two_way_msg_subject():
    return TwoWayMessageSubjectFactory()


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
def permissionset_administer_sources(db):
    ps = PermissionSetFactory(name="Administer Sources")

    perm_specs = [
        ("add_source", "observations", "source"),
        ("change_source", "observations", "source"),
        ("view_source", "observations", "source"),
        ("delete_source", "observations", "source"),
        ("view_sourcegroup", "observations", "sourcegroup"),
    ]

    perms = [Permission.objects.get_by_natural_key(*perm_spec) for perm_spec in perm_specs]
    ps.permissions.add(*perms)
    return ps


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


@pytest.fixture
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
def display_category():
    return DisplayCategoryFactory.create()


@pytest.fixture
def gear_subjectsource():
    return GearFactory.create()


@pytest.fixture
def gear_subjectsource_with_observations():
    gear_subjectsource = GearFactory.create()

    subject_type = SubjectTypeFactory(value="gear")
    subject_subtype, _ = SubjectSubType.objects.get_or_create(
        value="ropeless_buoy_device", defaults={"display": "Ropeless Buoy Device", "subject_type": subject_type}
    )
    gear_subjectsource.subject.subject_subtype = subject_subtype
    gear_subjectsource.subject.is_active = True
    gear_subjectsource.save()

    source = gear_subjectsource.source
    provider = gear_subjectsource.source.provider
    provider.save()
    now = timezone.now()
    additional = generate_devices(2)
    additional["event_type"] = "gear_deployed"
    location_dict = json.loads(additional["devices"][0])["location"]
    point = Point(location_dict["longitude"], location_dict["latitude"])
    data = {
        "recorded_at": now,
        "location": point,
        "source": source,
        "additional": additional,
    }

    observation = Observation.objects.create(**data)
    observation.save()

    gear_subjectsource.subject.additional = additional
    gear_subjectsource.subject.save()

    return gear_subjectsource


@pytest.fixture
def five_gears():
    return GearFactory.create_batch(5)


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
def cat1_cat2_categories():
    cat1 = EventCategoryFactory.create(value="cat1")
    cat2 = EventCategoryFactory.create(value="cat2")
    return cat1, cat2


@pytest.fixture
def five_event_categories():
    categories_codename = [
        {"value": "analyzer_event", "display": "Analyzer Event"},
        {"value": "security", "display": "Security"},
        {"value": "monitoring", "display": "Monitoring"},
        {"value": "logistics", "display": "Logistics"},
        {"value": "test", "display": "Test"},
    ]

    categories = []
    for values in categories_codename:
        categories.append(EventCategoryFactory.create(**values))
    return categories


@pytest.fixture
def patrol_type():
    return PatrolTypeFactory.create()


@pytest.fixture
def event_type():
    return EventTypeFactory.create()


@pytest.fixture
def five_event_types():
    return EventTypeFactory.create_batch(5)


@pytest.fixture
def cat1_cat2_event_types(cat1_cat2_categories):
    """
    Creates a controlled batch of V2 EventTypes:
      - Two event types in category "cat1" (active)
      - One event type in category "cat2" (active)
      - One inactive event type in category "cat1"
      - One event type in category "cat1" with is_collection=True
    """
    event_type_class = apps.get_model(app_label="activity", model_name="EventType")
    v2 = event_type_class.VersionChoices.VERSION_2
    cat1, cat2 = cat1_cat2_categories

    schema = json.dumps(
        {
            "json": {
                "type": "object",
                "properties": {
                    "subjects_name": {"type": "string", "title": "enum test"},
                    "behavior_choice": {"type": "string", "title": "name and value test"},
                    "behavior": {"type": "array", "title": "array test"},
                    "sample_attr": {"type": "string", "title": "name and value test"},
                    "estimated_time_of_occurrence": {
                        "deprecated": False,
                        "description": "",
                        "format": "date-time",
                        "title": "Estimated time of occurrence",
                        "type": "string",
                    },
                },
                "additionalProperties": False,
                "required ": [
                    "subjects_name",
                    "behavior_choice",
                    "behavior",
                    "sample_attr",
                    "estimated_time_of_occurrence",
                ],
            },
            "ui": {
                "fields": {
                    "estimated_time_of_occurrence": {"type": "DATE_TIME", "parent": "section-y-ya0voZLC9hP-zS86FzC"},
                }
            },
        }
    )

    et1 = EventTypeFactory.create(category=cat1, is_active=True, is_collection=False, version=v2, schema=schema)
    et2 = EventTypeFactory.create(category=cat1, is_active=True, is_collection=True, version=v2, schema=schema)
    et3 = EventTypeFactory.create(category=cat2, is_active=True, is_collection=False, version=v2, schema=schema)
    et4 = EventTypeFactory.create(category=cat1, is_active=False, is_collection=False, version=v2, schema=schema)
    et5 = EventTypeFactory.create(category=cat1, is_active=True, is_collection=False, version=v2, schema=schema)
    return [et1, et2, et3, et4, et5]


@pytest.fixture(autouse=True)
def dummy_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake",
            "KEY_FUNCTION": "utils.tenant.cache.make_cache_key",
        },
        settings.SHARED_CACHE_ALIAS: {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "shared-cache",
            "KEY_PREFIX": "shared",
        },
    }


@pytest.fixture
def event():
    return EventFactory.create()


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
def application():
    application, _ = Application.objects.get_or_create(client_id="das_web_client")
    return application


@pytest.fixture
def create_user(das_tenant):
    def _create_user(is_superuser=False, is_staff=False, das_tenant=das_tenant, **kwargs):
        kwargs.setdefault("das_tenant", das_tenant)
        kwargs.setdefault("is_superuser", is_superuser)
        kwargs.setdefault("is_staff", is_staff)
        return UserFactory(**kwargs)

    return _create_user


@pytest.fixture
def superuser(create_user):
    return create_user(is_superuser=True, is_staff=True)


@pytest.fixture
def user(create_user):
    return create_user()


@pytest.fixture
def create_client_for_user(application, tenant):
    def _create_client_for_user(user, application=application, tenant=tenant):
        with TenantContextManager(domain=tenant.domain):
            token = AccessTokenFactory(user=user, application=application).token
        client = APIClientWithUser()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        client.force_login(user=user)
        client.user = user
        return client

    return _create_client_for_user


@pytest.fixture
def superuser_client(create_client_for_user, superuser):
    return create_client_for_user(superuser)


@pytest.fixture
def user_client(create_client_for_user, user):
    return create_client_for_user(user)


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
def tenant_document_cache_client_mock(monkeypatch, tenant_response):
    tenant_document_cache_client_mock = MagicMock()
    tenant_document_cache_client_mock.get_key.return_value = json.dumps(tenant_response)
    monkeypatch.setattr("utils.tenant.providers.tenant_document_cache_client", tenant_document_cache_client_mock)
    return tenant_document_cache_client_mock


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


@pytest.fixture
def tenant_two(request, monkeypatch, one_tenant):
    """Return a DASTenant and a matching tenant settings object.
    Additionally the initial data has been loaded into the db for this tenant"""
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

    def get_tenant_domain_from_alt_server_name(alt_server_name):
        if alt_server_name in tenant.env_settings.alt_server_names:
            return tenant.domain

    monkeypatch.setattr(
        "utils.tenant.providers.get_tenant_domain_from_alt_server_name", get_tenant_domain_from_alt_server_name
    )
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


@pytest.fixture
def subject_source_with_observations():
    subject_source = SubjectSourceFactory()
    observation = ObservationFactory(source=subject_source.source)
    SubjectStatus.objects.maintain_subject_status(subject_source.subject.id)
    return subject_source, observation


@pytest.fixture
def subject_source_with_older_observation_past_show_track_days_since():
    subject_source = SubjectSourceFactory()
    recorded_at = timezone.now() - timedelta(days=settings.SHOW_TRACK_DAYS + 1)
    observation = ObservationFactory(recorded_at=recorded_at, source=subject_source.source)
    return subject_source, observation


@pytest.fixture(scope="function")
def add_view_to_urls():
    """
    Returns a function that can add views "on the fly" to a temporary URL patterns list under the "tests" namespace.

    This fixture is scoped to function level to ensure proper isolation between tests.
    """
    from django.urls import clear_url_caches

    from das_server.urls import urlpatterns as root_urlpatterns

    temp_urlpatterns = []
    # Create a unique namespace for this test run to avoid conflicts
    test_id = str(uuid.uuid4()).replace("-", "")[:8]
    namespace = f"tests_{test_id}"

    root_urlpatterns.insert(
        0,
        path(
            f"api/v1.0/tests/{test_id}/",
            include((temp_urlpatterns, namespace)),
            name=namespace,
        ),
    )

    clear_url_caches()

    def _add_view(
        view_class: Type[View],
        route: Optional[str] = None,
        name: Optional[str] = None,
        initkwargs: Optional[dict] = None,
    ):
        initkwargs = {} if initkwargs is None else initkwargs
        if route is None or name is None:
            view_id = str(uuid.uuid4()).replace("-", "")[:8]
            route = f"view_{view_id}/"
            name = view_id

        temp_urlpatterns.append(path(route, view_class.as_view(**initkwargs), name=name))
        clear_url_caches()
        return f"{namespace}:{name}"

    yield _add_view

    # Cleanup: Remove our added URL pattern
    del root_urlpatterns[0]
    clear_url_caches()


@pytest.fixture
def json_schema_fixture(request):
    fixture_name = request.param

    fixture_path = Path(__file__).parent.parent / "fixtures" / f"{fixture_name}.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def disable_close_old_connections(monkeypatch):
    """
    Disables the server's use of Django's close_old_connections() function during tests to prevent connection already closed errors.
    """
    monkeypatch.setattr("rt_api.views.close_old_connections", lambda: None)
    monkeypatch.setattr("rt_api.tasks.close_old_connections", lambda: None)
    monkeypatch.setattr("rt_api.management.commands.rtserver.close_old_connections", lambda: None)
    monkeypatch.setattr("utils.db.connections.close_old_shared_connections", lambda: None)
