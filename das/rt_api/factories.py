import factory
from factory import fuzzy

from observations.models import UserSession


class UserSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserSession

    sid = fuzzy.FuzzyText(length=40)
