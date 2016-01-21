import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, Polygon, MultiPolygon

from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL
from mapping.models import PolygonFeature

logger = logging.getLogger(__name__)


class ProximityAnalyzer(Analyzer):
    """ Speed Analyzer for a Track. """

    polygon = models.ForeignKey(to=PolygonFeature)

    # default box around africa
    _default_polygon = MultiPolygon(
        Polygon((
            (-20, 40),
            (60, 40),
            (60, -40),
            (-20, -40),
            (-20, 40)
        ))
    )

    @property
    def polygon_or_default(self):
        try:
            return self.polygon
        except:
            # create the objects, but we don't need to save() them
            feature_type = FeatureType(name='')

            poly = PolygonFeature(
                presentation={},
                feature_geometry=self._default_polygon,
                type=feature_type
            )
            return poly

    def analyze(self, track):
        """ analyze track for proximity conditions. Only the 24 hours before the most
        recent observation are considered """

        super().analyze(track)

        result = AnalyzerResult()
        result.analyzer_type = self.__class__.__name__

        # TODO: Is track proximal to poly?

        if result.level > NOMINAL:
            logger.info('Speed Analyzer detected exceeded speed threshold')

        return result
