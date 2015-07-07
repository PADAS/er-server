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
import django.contrib.postgres as postgres

class OOI(models.Model):
    """Object of Interest"""
    pass


class Observation(models.Model):
    """observation point

    similar to archive_loc

    """
    objects = models.GeoManager()

    def __str__(self):
        return self.name
