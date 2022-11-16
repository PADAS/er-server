import pytest

from activity.factories import (EventFactory, EventSourceEventFactory,
                                EventSourceFactory)


@pytest.fixture
def base_event():
    return EventFactory.create()


@pytest.fixture
def event_source_event():
    return EventSourceEventFactory.create()


@pytest.fixture
def event_with_event_source_event(base_event):
    EventSourceEventFactory.create(event=base_event)
    return base_event


@pytest.fixture
def event_source():
    return EventSourceFactory.create()
