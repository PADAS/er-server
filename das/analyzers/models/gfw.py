import logging
import uuid

from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TimestampedModel

logger = logging.getLogger(__name__)


class GlobalForestWatchSubscription (TimestampedModel):
    # GLAD Confidence Level
    BOTH_CONFIRMED_UNCONFIRMED = '2, 3'
    CONFIRMED = '3'

    # VIIRS Confidence Level
    HIGH = 'high'
    HIGH_NOMINAL = 'high, nominal'
    ALL = 'high, nominal, low'

    DEFORESTATION_ALERTS_CONFIDENCE_CHOICES = [
        (CONFIRMED, 'Confirmed Only'),
        (BOTH_CONFIRMED_UNCONFIRMED, 'Confirmed and Unconfirmed'),
    ]

    FIRE_ALERTS_CONFIDENCE_CHOICES = [
        (HIGH, 'High Only'),
        (HIGH_NOMINAL, 'High and Nominal'),
        (ALL, 'High, Nominal and Low'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=100)
    subscription_id = models.CharField(max_length=100, blank=True)
    geostore_id = models.CharField(max_length=100,  blank=True)
    additional = models.JSONField(
        default=dict, help_text='JSON data for subscriptions', blank=True)
    Deforestation_confidence = models.CharField(max_length=100,
                                                choices=DEFORESTATION_ALERTS_CONFIDENCE_CHOICES,
                                                default=CONFIRMED)
    Fire_confidence = models.CharField(max_length=100,
                                       choices=FIRE_ALERTS_CONFIDENCE_CHOICES,
                                       default=HIGH_NOMINAL)

    subscription_geometry = models.PolygonField(
        geography=True, srid=4326, null=True)
    last_check_time = models.DateTimeField(blank=True, null=True)
    last_check_status = models.CharField(max_length=100, blank=True)
    glad_confirmed_backfill_days = models.IntegerField(default=180)

    class Meta:
        verbose_name = 'Global Forest Watch Subscription'
        verbose_name_plural = 'Global Forest Watch Subscriptions'
