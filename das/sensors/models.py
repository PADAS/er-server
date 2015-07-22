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
from django.contrib.postgres.fields import DateTimeRangeField, ArrayField
from django.utils import timezone
import pytz

class Device(models.Model):
    """Collar, MotoTrbo, sensor, etc"""
    id = models.AutoField(primary_key=True)
    device_type = models.ForeignKey('DeviceType')
    manufacturer_id = models.CharField('device manufacturer id', max_length=100,
                                       null=True)
    additional = JsonBField()


class DeviceType(models.Model):
    """Device characteristics"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    categories = ArrayField(models.CharField(max_length=50, blank=True))
    additional = JsonBField()


class Observation(models.Model):
    """observation point

    similar to archive_loc

    """
    id = models.AutoField(primary_key=True)
    location = models.PointField()
    recorded_at = models.DateTimeField() #point in time of object at lat lon
    created_at = models.DateTimeField(auto_now_add=True) #date/time this row created
    device = models.ForeignKey('Device')
    additional = JsonBField()

    objects = models.GeoManager()

    def __str__(self):
        return self.name



class SubjectDevice(models.Model):
    """A Subject is associated with a Device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """
    id = models.AutoField(primary_key=True)
    assigned_range = DateTimeRangeField()
    device = models.ForeignKey('Device')
    subject = models.ForeignKey('Subject')
    additional = JsonBField()
    """EXCLUDE USING gist (device_id WITH =, assigned_range WITH &&)"""


class Subject(models.Model):
    """Person, Animal, Vehicle, etc"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    additional = JsonBField()


# TODO: should go in Import/Transformer django app
# class CollectionHistory(models.Model):
#     """Input Transformer log"""
#     created_at = models.DateTimeField(auto_now_add=True) #date/time this row created
#     device = models.ForeignKey('Device')
#     outcome = models.CharField(max_length=50)

MARKER_ICONS = {
    'elephant-male': 'http://107.21.94.89/Images/AnimalIcons/Elephant_Male.png',
    'elephant-female': 'http://107.21.94.89/Images/AnimalIcons/Elephant_Female.png',
    'lion-male': '',
    'vehicle': 'http://maps.google.com/mapfiles/kml/shapes/truck.png',
    'cow': '',
    'cheetah': '',
    'expedition': 'http://maps.google.com/mapfiles/kml/shapes/triangle.png',
    'zebra': 'http://107.21.94.89/Images/AnimalIcons/GrevysZebra_Female.png',
    'forest elephant': '',
    'goat': '',
    'sable': '',
    'white rhino': '',
    'black rhino': '',
}
def googlemarkericon(subject_type):
    return MARKER_ICONS.get(subject_type, 'http://maps.google.com/mapfiles/kml/shapes/truck.png')