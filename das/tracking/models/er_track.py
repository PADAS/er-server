import logging
import uuid

from django.contrib.gis.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.utils.translation import gettext_lazy as _

from core.models import TimestampedModel
from observations.models import SourceProvider, SubjectType

logger = logging.getLogger(__name__)

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


class SourceProviderConfiguration(TimestampedModel):

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
        SubjectType, related_name='name_change_excluded_subject_types',
        default='wildlife', blank=True, verbose_name='')

    is_default = models.BooleanField(verbose_name=_('Use as default?'),
                                     help_text=_(
                                         'Used this as the default configuration'),
                                     default=True)

    source_provider = models.OneToOneField(to=SourceProvider, null=True, blank=True, on_delete=models.SET_NULL,
                                           help_text=_('This configuration will be used for this SourceProvider'))
    new_device_match_case = models.BooleanField(
        default=False, verbose_name="Match case")
    name_change_match_case = models.BooleanField(
        default=False, verbose_name="Match case")

    class Meta:
        verbose_name = 'EarthRanger Track Configuration'
        constraints = [UniqueConstraint(fields=['is_default'],
                                        condition=Q(is_default=True), name='default_track_config')]
