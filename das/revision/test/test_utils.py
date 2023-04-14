import pytest

from django.contrib.gis.geos import Point

from revision.manager import format_field, get_revision_message
from utils.text import humanize_field_name


class TestFormatField:
    @pytest.mark.parametrize(
        "latitude,longitude,format_",
        [
            (20.663385393265447, -103.29153988109354, "location"),
            (0, 0, "location"),
        ],
    )
    def test_format_with_location_and_field(self, latitude, longitude, format_):
        point = Point(srid=4326, x=longitude, y=latitude)

        formatted_field = format_field(str(point), format_)

        assert formatted_field == f"{latitude}°, {longitude}°"

    @pytest.mark.parametrize("format_", ["location"])
    def test_format_location_without_field(self, format_):
        formatted_field = format_field("", format_)
        assert formatted_field == ""

    @pytest.mark.parametrize("field,format_", [(10, "str"), ("field", "str")])
    def test_format_field_as_string(self, field, format_):
        formatted_field = format_field(field, format_)

        assert formatted_field == field

    @pytest.mark.parametrize("field,format_,value", [(0, "priority", "Gray"), (100, "priority", "Green")])
    def test_format_field_as_priority(self, field, format_, value):
        formatted_field = format_field(field, format_)
        assert formatted_field == value


class TestRevisionMessage:
    @pytest.mark.parametrize(
        "data",
        [
            {"field_name": "title", "previous_value": "Old Title", "value": "New title"},
            {"field_name": "state", "previous_value": "active", "value": "resolved"},
        ],
    )
    def test_get_revision_message_with_previous_value(self, data):
        message = get_revision_message(**data)

        assert (
            message == f"Changed {humanize_field_name(data['field_name'])}: {data['previous_value']} → {data['value']}"
        )

    @pytest.mark.parametrize(
        "data",
        [
            {"field_name": "title", "previous_value": "", "value": "My TiTle"},
            {"field_name": "state", "previous_value": "", "value": "active"},
        ],
    )
    def test_get_revision_message_without_previous_value(self, data):
        message = get_revision_message(**data)

        assert message == f"Added {humanize_field_name(data['field_name'])}: {data['value']}"

    @pytest.mark.parametrize(
        "data",
        [
            {
                "field_name": "location",
                "previous_value": str(Point(srid=4326, x=0, y=0)),
                "value": str(Point(srid=4326, x=-103.42058192459741, y=20.67125784725795)),
            },
            {
                "field_name": "location",
                "previous_value": str(Point(x=-103.12822680096475, y=20.720047089198403)),
                "value": str(Point(x=-103.0747947517758, y=20.322855565455136)),
            },
        ],
    )
    def test_get_revision_message_for_location_with_previous_value(self, data):
        message = get_revision_message(**data)

        formatted_value = format_field(data["value"], "location")
        formatted_previous_value = format_field(data["previous_value"], "location")

        assert message == f"Changed {humanize_field_name('location')}: {formatted_previous_value} → {formatted_value}"

    @pytest.mark.parametrize(
        "data",
        [
            {
                "field_name": "location",
                "previous_value": "",
                "value": str(Point(srid=4326, x=-103.42058192459741, y=20.67125784725795)),
            },
            {
                "field_name": "location",
                "previous_value": "",
                "value": str(Point(x=-103.42058192459741, y=20.67125784725795)),
            },
        ],
    )
    def test_get_revision_message_for_location_without_previous_value(self, data):
        message = get_revision_message(**data)

        formatted_field = format_field(data["value"], "location")

        assert message == f"Added Location: {formatted_field}"
