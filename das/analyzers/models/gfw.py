import logging
import uuid

from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
from django.utils.translation import ugettext_lazy as _

from core.models import TimestampedModel

logger = logging.getLogger(__name__)


class GlobalForestWatchSubscription (TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=100)
    subscription_id = models.CharField(max_length=100, blank=True)
    geostore_id = models.CharField(max_length=100,  blank=True)
    additional = JSONField(default=dict, help_text='JSON data for subscriptions', blank=True)

    subscription_geometry = models.PolygonField(geography=True, srid=4326, null=True)

    class Meta:
        verbose_name = 'Global Forest Watch Subscription'
        verbose_name_plural = 'Global Forest Watch Subscriptions'

