"""
DAS DB models

after making changes to a model run migrations to record changes:
* python manage.py makemigrations --name "interesting model change name"

To re-sync your database with changes from others
* python manage.py migrate


GIS
* default geodjango spatial reference system is WGS84 (SRID 4326)
"""

from django.contrib.gis.db import models
from django_pgjson.fields import JsonBField


class Device(models.Model):
    """Collar, MotoTrbo, sensor, etc"""
    id = models.AutoField(primary_key=True)
    device_type = models.ForeignKey('DeviceType')
    extra = JsonBField()

class DeviceType(models.Model):
    """Device characteristics"""
    id = models.AutoField(primary_key=True)
    name = models.CharField()
    extra = JsonBField()

class Observation(models.Model):
    """observation point

    similar to archive_loc

    """
    id = models.AutoField(primary_key=True)
    location = models.GeometryField()
    lat = models.FloatField()
    lon = models.FloatField()
    recorded_at = models.DateTimeField() #point in time of object at lat lon
    created_at = models.DateTimeField(auto_now_add=True) #date/time this row created
    device = models.ForeignKey('Device')
    extra = JsonBField()

    objects = models.GeoManager()

    def __str__(self):
        return self.name


class ThingDevice(models.Model):
    """A Thing is associated with a Device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """
    start_at =  models.DateTimeField()
    end_at = models.DateTimeField()
    device = models.ForeignKey('Device')
    thing = models.ForeignKey('Thing')
    extra = JsonBField()

class Thing(models.Model):
    """Person, Animal, Vehicle, etc"""
    extra = JsonBField()

class CollectionHistory(models.Model):
    """Input Transformer log"""
    created_at = models.DateTimeField(auto_now_add=True) #date/time this row created
    device = models.ForeignKey('Device')
    outcome = models.CharField()