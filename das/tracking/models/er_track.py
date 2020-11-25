from django.contrib.gis.db import models
from django.db.models import Q
from core.models import TimestampedModel
from django.utils.translation import ugettext_lazy as _
from observations.models import SubjectType
import uuid
from django.db.models.constraints import UniqueConstraint
from django.db import transaction

CREATE_NEW = 'create_new'
USE_EXISTING = 'use_existing'
UPDATE_NAME = 'update_name'

NEW_SUBJECT_CONFIG_CHOICES = (
    (CREATE_NEW, 'Create a new subject'),
    (USE_EXISTING, 'Use existing matching subject'))

NAME_CHANGE_CONFIG_CHOICES = (
    (CREATE_NEW, 'Create a new subject'),
    (USE_EXISTING, 'Use existing matching subject'),
    (UPDATE_NAME, 'Update the name of the existing subject'))

DEFAULT_CONFIG = 'default_config'
TRACT_CONFIGURATION_CHOICES = (
    (DEFAULT_CONFIG, 'Default Configuration'),
)


class TrackConfiguration(TimestampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    new_device_config = models.CharField(
        choices=NEW_SUBJECT_CONFIG_CHOICES, default=USE_EXISTING,
        max_length=50, verbose_name="New device setting",
        help_text=_('Specifies whether to create a new subject or use an existing one with a name that matches the device name when setting up a new device.'))

    name_change_config = models.CharField(
        choices=NAME_CHANGE_CONFIG_CHOICES, default=USE_EXISTING,
        max_length=50, verbose_name="Name change setting",
        help_text=_('Specifies whether to update the existing subject name, create a new subject, or reassign to an existing subject with a name that matches the new device name.'))

    new_subject_excluded_subject_types = models.ManyToManyField(
        SubjectType, related_name='new_subject_excluded_subject_types',
        default='wildlife', blank=True, verbose_name='')

    name_change_excluded_subject_types = models.ManyToManyField(
        SubjectType, related_name='name_change_excluded_subject_types', default='wildlife',
        help_text=_('Select any Subject Types to exclude from matching'))
    configuration_type = models.CharField(
        default=DEFAULT_CONFIG, choices=TRACT_CONFIGURATION_CHOICES, max_length=50)

    class Meta:
        verbose_name = 'EarthRanger Track Configuration'
        constraints = [UniqueConstraint(fields=['configuration_type'],
                                        condition=Q(configuration_type=DEFAULT_CONFIG), name='default_track_configuration')]

