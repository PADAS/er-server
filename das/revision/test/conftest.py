import pytest

from activity.models import PRI_NONE


@pytest.fixture
def event_payload():
    return {
        "event_type": "acoustic_detection",
        "state": "active",
        "title": "TITLE",
        "priority": PRI_NONE,
        "time": "2023-03-09T22:25:20.329Z",
    }
