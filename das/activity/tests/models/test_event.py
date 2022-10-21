from unittest.mock import patch

import pytest

from activity.models import Event


@pytest.mark.django_db
class TestEvent:
    def test_delete_geometries_updates_event(self, event_geometry_with_polygon):
        with patch.object(Event, "dependent_table_updated") as event_updated_mock:
            event = event_geometry_with_polygon.event
            event.geometries.all().delete()

            event_updated_mock.assert_called_once()
