import factory
from factory import fuzzy
from django.contrib.auth.hashers import make_password

from activity.models import Patrol, PatrolNote, PatrolType, PatrolSegment
from accounts.models.user import User
from observations.models import Subject


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


class SubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subject

    name = fuzzy.FuzzyText(length=50)


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
