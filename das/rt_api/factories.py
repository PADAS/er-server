import factory

from observations.models import UserSession


class UserSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserSession
