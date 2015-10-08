import uuid

from django.contrib.gis.db import models
from django_pgjson.fields import JsonBField

from core.models import TimestampedModel


class FeatureType(TimestampedModel):
    """
    If the clients wish to group layers in a control or for ease of administration
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)


class FeatureSet(TimestampedModel):
    """
    A grouping of features that should be toggled together on the map,
      e.g. a set of camps or a system of rivers
      ... better than handling as a layer group in UI as it allows grouping to be controlled in db?
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)
    type = models.ForeignKey(to=FeatureType)

    description = models.TextField(null=True, blank=True)

    # todo:  perhaps type and name?
    def __str__(self):
        return u"{0}".format(self.name)


class Feature(TimestampedModel):
    """
    A vector feature, e.g. a boundary, a hut, a village, a river ...
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)
    type = models.ForeignKey(to=FeatureType)

    description = models.TextField(null=True, blank=True)

    # attributes for presentation
    presentation = JsonBField()

    # the feature set with which this feature is being grouped.
    # todo:  evaluate whether many-to-many might be a better approach or stick with this simple approach
    featureset = models.ForeignKey(to=FeatureSet, null=True)

    class Meta:
        abstract = True

    # todo:  perhaps type and name?
    def __str__(self):
        return u"{0}".format(self.name)


class PolygonFeature(Feature):
    feature_geometry = models.MultiPolygonField(srid=4326)


class LineFeature(Feature):
    feature_geometry = models.MultiLineStringField(srid=4326)


class PointFeature(Feature):
    feature_geometry = models.MultiPointField(srid=4326)

