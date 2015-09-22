import uuid

from django.contrib.gis.db import models
from django_pgjson.fields import JsonBField

from core.models import TimestampedModel



class BaseMap(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)

    description = models.TextField(null=True, blank=True)

    # todo:  actually a reference to the uploaded tif ...
    raster_file = models.CharField(max_length=80, unique=True)

    # todo:  perhaps type and name?
    def __str__(self):
        return u"{0}".format(self.name)



class Feature(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)
    # todo:  placeholder for a type vocabulary
    type = models.CharField(max_length=80)

    description = models.TextField(null=True, blank=True)

    # attributes for presentation
    presentation = JsonBField()

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