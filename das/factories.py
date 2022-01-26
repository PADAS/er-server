import factory
from accounts.models.user import User
from activity.models import (
    EventCategory,
    EventType,
    Patrol,
    PatrolNote,
    PatrolSegment,
    PatrolType,
    Event,
    EventDetails,
)
from analyzers.models import FeatureProximityAnalyzerConfig, GeofenceAnalyzerConfig
from django.contrib.auth.hashers import make_password
from factory import fuzzy
from mapping.models import SpatialFeatureGroupStatic, SpatialFeatureType
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectGroup,
    SubjectSource,
    SubjectSubType,
    SubjectType,
)


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

    name = fuzzy.FuzzyText(length=40)


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

    value = fuzzy.FuzzyText(length=20)


class EventTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventType

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
    data = factory.LazyAttribute(lambda data: {})
