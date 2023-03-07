import factory
from factory import fuzzy

from activity.libs import constants as activities_constants
from activity.models import EventProvider, EventSource, EventsourceEvent
from factories import EventFactory


class EventProviderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventProvider
    additional = factory.LazyAttribute(lambda data: {
        "external_event_url": activities_constants.EventTestsConstants.url,
        "icon_url": activities_constants.EventTestsConstants.icon_url})
    display = fuzzy.FuzzyText(length=20)


class EventSourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventSource

    display = fuzzy.FuzzyText(length=20)
    eventprovider = factory.SubFactory(EventProviderFactory)


class EventSourceEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventsourceEvent

    event = factory.SubFactory(EventFactory)
    eventsource = factory.SubFactory(EventSourceFactory)
