from decimal import Decimal

import pytest

from django.contrib.gis.geos import Polygon

from utils.gis import get_polygon_info


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
                {"area": 18096, "perimeter": 539},
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
