from unittest.mock import patch

import pytest

from django.contrib.gis.geos import Polygon

from activity.models import Event, EventGeometry


@pytest.mark.django_db
class TestEventGeometry:
    def test_creating_geometry_for_an_event(self, event_with_detail):
        EventGeometry.objects.create(
            event=event_with_detail.event,
            geometry=Polygon(
                (
                    (-103.41898441314697, 20.638567565077864),
                    (-103.41387748718262, 20.63499318125139),
                    (-103.40585231781006, 20.646840535793658),
                    (-103.41898441314697, 20.638567565077864)
                )
            )
        )

        assert event_with_detail.event.geometries.all().count()
        assert EventGeometry.objects.all().count()

    def test_add_geometry_should_update_event_related_instance(self, event_with_detail):
        with patch.object(Event, "dependent_table_updated") as event_update_mock:
            event = event_with_detail.event

            geometry = EventGeometry.objects.create(
                event=event,
                geometry=Polygon(
                    (
                        (-103.41898441314697, 20.638567565077864),
                        (-103.41387748718262, 20.63499318125139),
                        (-103.40585231781006, 20.646840535793658),
                        (-103.41898441314697, 20.638567565077864)
                    )
                )
            )

            event_update_mock.assert_called_once()

    def test_delete_all_geometries_should_update_event_related_instance(
        self,
        event_geometry_with_polygon
    ):
        event = event_geometry_with_polygon.event
        with patch.object(Event, "dependent_table_updated") as event_update_mock:
            event.geometries.all().delete()
            event_update_mock.assert_called_once()
