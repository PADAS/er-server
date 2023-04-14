import pytest

from utils.text import humanize_field_name


@pytest.mark.parametrize(
    "data",
    [
        {"field_name": "field_name", "expected": "Field name"},
        {"field_name": "event_time", "expected": "Event time"},
        {"field_name": "event_type", "expected": "Event type"},
        {"field_name": "created_by_user", "expected": "Created by user"},
    ],
)
def test_humanize_field_name(data):
    humanized_field_name = humanize_field_name(data["field_name"])

    assert humanized_field_name == data["expected"]
