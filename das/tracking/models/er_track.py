from django.contrib.gis.db import models
from django.db.models import Q
from core.models import TimestampedModel
from django.utils.translation import ugettext_lazy as _
from observations.models import SubjectType, SourceProvider
import uuid
from django.db.models.constraints import UniqueConstraint

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
        SubjectType, related_name='name_change_excluded_subject_types',
        default='wildlife', blank=True,
        help_text=_('Select any Subject Types to exclude from matching'))
    is_default = models.BooleanField(_('default subject group'), default=False)
    source_provider = models.OneToOneField(to=SourceProvider, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = 'EarthRanger Track Configuration'
        constraints = [UniqueConstraint(fields=['is_default'],
                                        condition=Q(is_default=True), name='default_track_config')]
