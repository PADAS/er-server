import datetime
import uuid

import factory
from factory import fuzzy
from factory.fuzzy import BaseFuzzyAttribute
from oauth2_provider.models import AccessToken

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.gis.geos import Polygon
from django.utils import timezone

from accounts.models.permissionset import PermissionSet
from activity.models import (Event, EventCategory, EventDetails, EventGeometry,
                             EventNote, EventType, Patrol, PatrolNote,
                             PatrolSegment, PatrolType)
from analyzers.models import (FeatureProximityAnalyzerConfig,
                              GeofenceAnalyzerConfig)
from mapping.models import SpatialFeatureGroupStatic, SpatialFeatureType
from observations.models import (Observation, Source, SourceProvider, Subject,
                                 SubjectGroup, SubjectSource, SubjectSubType,
                                 SubjectType)

User = get_user_model()


class PermissionSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PermissionSet
        django_get_or_create = ('name',)

    name = fuzzy.FuzzyText(length=25)

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for permissions in extracted:
                self.permissions.add(permissions)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: "username{}".format(n))
    first_name = fuzzy.FuzzyText(length=25)
    last_name = fuzzy.FuzzyText(length=25)
    email = factory.Sequence(lambda n: "earthranger{}@example.com".format(n))
    password = factory.LazyFunction(lambda: make_password("pi3.1415"))


class PatrolFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Patrol

    title = fuzzy.FuzzyText(length=50)


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


class SubjectSubTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubjectSubType

    value = fuzzy.FuzzyText(length=20)
    display = fuzzy.FuzzyText(length=50)
    subject_type = factory.SubFactory(SubjectTypeFactory)


class SubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subject

    name = fuzzy.FuzzyText(length=50)
    subject_subtype = factory.SubFactory(SubjectSubTypeFactory)


class ProviderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SourceProvider

    display_name = fuzzy.FuzzyText(length=50)


class SourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Source

    manufacturer_id = fuzzy.FuzzyText(length=50)
    provider = factory.SubFactory(ProviderFactory)


class SubjectSourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubjectSource

    source = factory.SubFactory(SourceFactory)
    subject = factory.SubFactory(SubjectFactory)


class SubjectGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubjectGroup
        django_get_or_create = ('name',)

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


class PatrolSegmentSubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PatrolSegment

    patrol = factory.SubFactory(PatrolFactory)
    patrol_type = factory.SubFactory(PatrolTypeFactory)
    leader = factory.SubFactory(SubjectFactory)


class PatrolSegmentUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PatrolSegment

    patrol = factory.SubFactory(PatrolFactory)
    patrol_type = factory.SubFactory(PatrolTypeFactory)
    leader = factory.SubFactory(UserFactory)


class GeofenceAnalyzerConfigFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GeofenceAnalyzerConfig

    subject_group = factory.SubFactory(SubjectGroupFactory)


class FeatureProximityAnalyzerConfigFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeatureProximityAnalyzerConfig

    subject_group = factory.SubFactory(SubjectGroupFactory)


class SpatialFeatureGroupStaticFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SpatialFeatureGroupStatic


class SpatialFeatureTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SpatialFeatureType


class ObservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Observation


class EventCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventCategory
        django_get_or_create = ('value',)

    value = fuzzy.FuzzyText(length=20)


class EventTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventType
        django_get_or_create = ('value',)

    value = fuzzy.FuzzyText(length=20)
    display = fuzzy.FuzzyText(length=50)
    category = factory.SubFactory(EventCategoryFactory)


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    title = fuzzy.FuzzyText(length=20)
    event_type = factory.SubFactory(EventTypeFactory)


class EventDetailsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventDetails

    event = factory.SubFactory(EventFactory)
    data = factory.LazyAttribute(lambda data: {"event_details": {}})


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


class AccessTokenFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = AccessToken

    scope = "read write"

    @factory.lazy_attribute
    def token(self):
        return str(uuid.uuid4())

    @factory.lazy_attribute
    def expires(self):
        return timezone.now() + datetime.timedelta(days=1)
