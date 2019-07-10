import logging
import uuid

from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
from django.utils.translation import ugettext_lazy as _

from core.models import TimestampedModel
from mapping.models import SpatialFeatureGroupStatic

logger = logging.getLogger(__name__)


class GlobalForestWatchSubscription (TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=100)
    spatial_feature_group = models.ForeignKey(SpatialFeatureGroupStatic,
                                              related_name='+',
                                              on_delete=models.PROTECT,
                                              help_text='geographical area to monitor',
                                              null=True)
    subscription_id = models.CharField(max_length=100, blank=True)
    geostore_id = models.CharField(max_length=100,  blank=True)
    additional = JSONField(default=dict, help_text='JSON data for subscriptions', blank=True)
    # alert_types, geostore_id, gfw_subscription_id, subscription_name, webhook url

    class Meta:
        verbose_name = 'Global Forest Watch Subscription'
        verbose_name_plural = 'Global Forest Watch Subscriptions'

# requestbin, ngrok