import pytest

from activity.models import PRI_NONE
from factories import EventTypeFactory


@pytest.fixture
def event_payload():
    return {
        "event_type": "acoustic_detection",
        "state": "active",
        "title": "TITLE",
        "priority": PRI_NONE,
        "time": "2023-03-09T22:25:20.329Z",
    }


@pytest.fixture
def acoustic_detection_event_type():
    # The data migration that ships `acoustic_detection` runs against the
    # default migration tenant, not the singleton used by EventTypeFactory.
    # Tests that POST `event_type=acoustic_detection` need this row in the
    # factory tenant so EventType.objects.get_by_value() resolves it.
    return EventTypeFactory(value="acoustic_detection", display="Acoustic Detection")
