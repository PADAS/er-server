from factory.django import DjangoModelFactory

from choices.models import Choice


class ChoiceFactory(DjangoModelFactory):
    class Meta:
        model = Choice
