from typing import Any

from django.contrib.gis.db.models import GeometryField
from django.db.models import Lookup

GEO_TYPE_POINT = "POINT"
GEO_TYPE_LINESTRING = "LINESTRING"
GEO_TYPE_POLYGON = "POLYGON"
GEO_TYPE_MULTIPOINT = "MULTIPOINT"
GEO_TYPE_MULTILINESTRING = "MULTILINESTRING"
GEO_TYPE_MULTIPOLYGON = "MULTIPOLYGON"


class GeometryTypeLookup(Lookup):  # type:ignore
    """
    Geometry type as a lookup
    """

    lookup_name = "type"
    prepare_rhs = False

    def as_sql(self, compiler: Any, connection: Any) -> Any:
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params

        return "GeometryType(%s) ILIKE %s" % (lhs, rhs), params


GeometryField.register_lookup(GeometryTypeLookup)
