import pytest

from django.contrib.gis.geos import Polygon

from activity.models import EventGeometry


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
