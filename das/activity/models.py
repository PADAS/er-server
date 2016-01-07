import uuid
import os
import logging
import glob
from django.contrib.auth.models import User

from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse, NoReverseMatch
from django.utils.translation import ugettext_lazy as _

from core.models import TimestampedModel
from das_utils.decorator import reify

logger = logging.getLogger(__name__)

PROVENANCES = (
    ('sensor', 'Sensor'),
    ('analyzer', 'Analyzer'),
    ('informant', 'Informant'),
)

EVENT_TYPES = (
    ('analyzer', 'Analyzer'),
    ('informant', 'Informant'),
)


class Event(TimestampedModel):
    """
    An Event is "something that has happened", recorded in the system.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)
    user = models.ForeignKey(User)
    provenance = models.CharField(max_length=20, choices=PROVENANCES, default='system')
    attributes = JSONField()
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='analyzer')
    location = models.PointField(srid=4326)

    def __str__(self):
        return self.name



