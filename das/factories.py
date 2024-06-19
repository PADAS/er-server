import uuid
from datetime import datetime, timedelta, timezone

import factory
from factory import fuzzy
from factory.fuzzy import BaseFuzzyAttribute
from oauth2_provider.models import get_access_token_model

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone

from accounts.models.permissionset import PermissionSet
from activity.models import (
    Community,
    Event,
    EventCategory,
    EventDetails,
    EventGeometry,
    EventNote,
    EventType,
    Patrol,
    PatrolNote,
    PatrolSegment,
    PatrolType,
)
from analyzers.models import FeatureProximityAnalyzerConfig, GeofenceAnalyzerConfig
from choices.models import Choice
from core.models import DASTenant
from mapping.models import SpatialFeatureGroupStatic, SpatialFeatureType
from observations.models import (
    Message,
    Observation,
    Source,
    SourceGroup,
    SourceProvider,
    Subject,
    SubjectGroup,
    SubjectSource,
    SubjectSubType,
    SubjectType,
)

AccessToken = get_access_token_model()
User = get_user_model()


class TenantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DASTenant
        django_get_or_create = ("id",)

    @classmethod
    def _adjust_kwargs(cls, **kwargs):
        if not isinstance(kwargs["id"], uuid.UUID):
            kwargs["id"] = uuid.UUID(kwargs["id"])
        return kwargs

    id = uuid.UUID("c0973be2-8e11-4cb8-8463-897fb96391d0")
    domain = "zoo.com"


class PermissionSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PermissionSet
        django_get_or_create = ("name",)

    name = fuzzy.FuzzyText(length=25)
    das_tenant = factory.SubFactory(TenantFactory)

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for permissions in extracted:
                self.permissions.add(permissions)


class PermissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Permission
        django_get_or_create = ("name",)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"username{n}")
    first_name = fuzzy.FuzzyText(length=25)
    last_name = fuzzy.FuzzyText(length=25)
    email = factory.Sequence(lambda n: f"earthranger{n}@example.com")
    password = factory.LazyFunction(lambda: make_password("pi3.1415"))


class PatrolFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Patrol

    title = fuzzy.FuzzyText(length=50)
    das_tenant = factory.SubFactory(TenantFactory)


class PatrolNoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PatrolNote

    text = fuzzy.FuzzyText(length=100)
    patrol = factory.SubFactory(PatrolFactory)


class PatrolTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PatrolType

    value = fuzzy.FuzzyText(length=30)
    display = fuzzy.FuzzyText(length=100)


class PatrolSegmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PatrolSegment

    patrol = factory.SubFactory(PatrolFactory)
    patrol_type = factory.SubFactory(PatrolTypeFactory)


class SubjectTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubjectType

    value = fuzzy.FuzzyText()
    display = fuzzy.FuzzyText()
    das_tenant = factory.SubFactory(TenantFactory)


class SubjectSubTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubjectSubType

    value = fuzzy.FuzzyText(length=20)
    display = fuzzy.FuzzyText(length=50)
    subject_type = factory.SubFactory(SubjectTypeFactory)
    das_tenant = factory.SubFactory(TenantFactory)


class SubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subject

    name = fuzzy.FuzzyText(length=50)
    subject_subtype = factory.SubFactory(SubjectSubTypeFactory)
    das_tenant = factory.SubFactory(TenantFactory)


class ProviderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SourceProvider

    display_name = fuzzy.FuzzyText(length=50)
    das_tenant = factory.SubFactory(TenantFactory)


class TwoWayMessageProviderFactory(ProviderFactory):
    class Params:
        two_way_messaging = True

    additional = {"two_way_messaging": True}


class SourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Source

    manufacturer_id = fuzzy.FuzzyText(length=50)
    provider = factory.SubFactory(ProviderFactory)
    das_tenant = factory.SubFactory(TenantFactory)


class SubjectSourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubjectSource

    source = factory.SubFactory(SourceFactory)
    subject = factory.SubFactory(SubjectFactory)
    das_tenant = factory.SubFactory(TenantFactory)


class SubjectGroupFactory(factory.django.DjangoModelFactory):
    das_tenant = factory.SubFactory(TenantFactory)

    class Meta:
        model = SubjectGroup
        django_get_or_create = ("name",)

    name = fuzzy.FuzzyText(length=40)

    @factory.post_generation
    def subjects(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for subject in extracted:
                self.subjects.add(subject)

    @factory.post_generation
    def permission_sets(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for permission_set in extracted:
                self.permission_sets.add(permission_set)


class TwoWayMessageSubjectFactory(SubjectFactory):
    @factory.post_generation
    def subjectsources(self, create, extracted, **kwargs):
        if extracted:
            for subjectsource in extracted:
                self.subjectsources.add(subjectsource)
        else:
            provider = TwoWayMessageProviderFactory(two_way_messaging=True)
            source = SourceFactory(provider=provider)
            self.subjectsources.add(SubjectSource.objects.create(subject=self, source=source))


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    text = fuzzy.FuzzyText(length=100)
    created_by_user = factory.SubFactory(UserFactory)
    subject = factory.SubFactory(TwoWayMessageSubjectFactory)
    message_time = (datetime.now(tz=timezone.utc),)


class PatrolSegmentSubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PatrolSegment

    patrol = factory.SubFactory(PatrolFactory)
    patrol_type = factory.SubFactory(PatrolTypeFactory)
    leader = factory.SubFactory(SubjectFactory)
    das_tenant = factory.SubFactory(TenantFactory)


class PatrolSegmentUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PatrolSegment

    patrol = factory.SubFactory(PatrolFactory)
    patrol_type = factory.SubFactory(PatrolTypeFactory)
    leader = factory.SubFactory(UserFactory)


class GeofenceAnalyzerConfigFactory(factory.django.DjangoModelFactory):
    das_tenant = factory.SubFactory(TenantFactory)

    class Meta:
        model = GeofenceAnalyzerConfig

    subject_group = factory.SubFactory(SubjectGroupFactory)


class FeatureProximityAnalyzerConfigFactory(factory.django.DjangoModelFactory):
    subject_group = factory.SubFactory(SubjectGroupFactory)
    das_tenant = factory.SubFactory(TenantFactory)

    class Meta:
        model = FeatureProximityAnalyzerConfig


class SpatialFeatureGroupStaticFactory(factory.django.DjangoModelFactory):
    das_tenant = factory.SubFactory(TenantFactory)

    class Meta:
        model = SpatialFeatureGroupStatic


class SpatialFeatureTypeFactory(factory.django.DjangoModelFactory):
    das_tenant = factory.SubFactory(TenantFactory)

    class Meta:
        model = SpatialFeatureType


class ObservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Observation

    recorded_at = factory.Sequence(lambda n: timezone.now() + timedelta(minutes=n * 5))
    source = factory.SubFactory(SourceFactory)

    @factory.lazy_attribute
    def location(self):
        return Point(-103.313486, 20.420935)


class EventCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventCategory
        django_get_or_create = ("value",)

    value = factory.Sequence(lambda n: f"value_{n}")
    display = factory.Sequence(lambda n: f"display_{n}")
    das_tenant = factory.SubFactory(TenantFactory)
    ordernum = factory.Sequence(lambda n: n)


class EventTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventType
        django_get_or_create = ("value",)

    value = fuzzy.FuzzyText(length=20)
    display = fuzzy.FuzzyText(length=50)
    category = factory.SubFactory(EventCategoryFactory)
    das_tenant = factory.SubFactory(TenantFactory)


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    title = fuzzy.FuzzyText(length=20)
    event_type = factory.SubFactory(EventTypeFactory)
    das_tenant = factory.SubFactory(TenantFactory)


class EventDetailsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventDetails

    event = factory.SubFactory(EventFactory)
    data = factory.LazyAttribute(lambda data: {"event_details": {}})
    das_tenant = factory.SubFactory(TenantFactory)


class EventNoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventNote

    text = fuzzy.FuzzyText(length=20)
    event = factory.SubFactory(EventFactory)
    created_by_user = factory.SubFactory(UserFactory)


class FuzzyPolygon(BaseFuzzyAttribute):
    def fuzz(self):
        return Polygon(
            (
                (-114.82910156249999, 33.17434155100208),
                (-80.5517578125, 25.443274612305746),
                (-104.2822265625, 48.86471476180277),
                (-114.82910156249999, 33.17434155100208),
            )
        )


class EventGeometryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventGeometry

    geometry = FuzzyPolygon()
    event = factory.SubFactory(EventFactory)
    das_tenant = factory.SubFactory(TenantFactory)


class AccessTokenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AccessToken

    scope = "read write"

    @factory.lazy_attribute
    def token(self):
        return str(uuid.uuid4())

    @factory.lazy_attribute
    def expires(self):
        return timezone.now() + timedelta(days=1)


class ChoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Choice

    model = Choice.User
    field = fuzzy.FuzzyText(length=10)
    value = factory.Sequence(lambda n: f"value_{n}")
    display = factory.Sequence(lambda n: f"display_{n}")
    ordernum = factory.Sequence(lambda n: n)


class CommunityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Community

    name = fuzzy.FuzzyText(length=10)


class SourceGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SourceGroup
