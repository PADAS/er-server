from decimal import Decimal

import pytest

from django.contrib.gis.geos import Polygon

from utils.gis import get_polygon_info, get_utm_by_wgs_84


class TestGis:
    @pytest.mark.parametrize(
        "coordinates,expected",
        (
            (
                [
                    [-103.38129937648773, 20.674454841539493],
                    [-103.38000923395157, 20.674454841539493],
                    [-103.38000923395157, 20.67551383792851],
                    [-103.38129937648773, 20.67551383792851],
                    [-103.38129937648773, 20.674454841539493],
                ],
                {"area": 15759, "perimeter": 503},
            ),
        ),
    )
    def test_get_polygon_info(self, coordinates, expected):
        polygon = Polygon(coordinates, srid=4326)
        area = get_polygon_info(polygon, "area")
        perimeter = get_polygon_info(polygon, "length")

        assert int(area) == expected["area"]
        assert int(perimeter) == expected["perimeter"]
        assert self._get_decimals_count(area) == 2
        assert self._get_decimals_count(perimeter) == 2

    def _get_decimals_count(self, number: float) -> int:
        return abs(Decimal(str(number)).as_tuple().exponent)

    @pytest.mark.parametrize(
        "coors,expected",
        [
            [{"latitude": 42.63417745560095, "longitude": -121.92225552234876}, 32610],
            [{"latitude": 20.927367751332778, "longitude": -102.45120663435452}, 32613],
            [{"latitude": -8.112994941042723, "longitude": -40.63553313639657}, 32724],
            [{"latitude": -42.141059503358996, "longitude": -66.01585547197922}, 32719],
        ],
    )
    def test_get_utm_by_wgs_84(self, coors, expected):
        epsg = get_utm_by_wgs_84(**coors)
        assert epsg == expected
