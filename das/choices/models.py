import uuid
from functools import partialmethod

from django.contrib.gis.db import models
from django.core import checks, exceptions
from django.db.models.fields import BLANK_CHOICE_DASH
from django.utils import timezone
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _

from core.utils import static_image_finder


class ChoiceQuerySet(models.QuerySet):
    def get_choices_for_field(self, model, field):
        result = self.get_choices(model, field)
        return result.get_values()

    def get_choices(self, model, field):
        return self.filter(model=model, field=field).order_by('ordernum')

    def get_values(self):
        return self.values_list('value', 'display')

    def get_filtered_q(self, parent_model, parent_field, parent_value):
        parent = self.all().get_choices(parent_model, parent_field).filter(
            value=parent_value)
        return models.Q(sub_choice_of=parent)

    def get_filtered_choices(self, parent_model, parent_field, parent_value):
        """after calling get_choices(), filter choices by parent values"""
        parent = self.all().get_choices(
            parent_model, parent_field).filter(value=parent_value)
        return self.filter(sub_choice_of=parent)

    def filter_active_choices(self):
        return self.filter(is_active=True)

    def filter_inactive_choices(self):
        return self.filter(is_active=False)

    def disable_choices(self):
        return self.update(delete_on=timezone.now(), is_active=False)

    def soft_delete(self):
        return self.disable_choices()


class DynamicChoice(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    model_name = models.CharField(max_length=100, verbose_name='Model lookup')
    criteria = models.CharField(max_length=100, verbose_name='Criteria')
    value_col = models.CharField(max_length=100, verbose_name='Value column')
    display_col = models.CharField(max_length=100,
                                   verbose_name='Display column')


class SoftDeleteModel(models.Model):
    delete_on = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def disable(self):
        self.delete_on = timezone.now()
        self.is_active = False
        self.save()


class Choice(SoftDeleteModel):

    Field_Reports = 'activity.event'
    User = 'accounts.user.User'
    Maps = 'mapping.TileLayer'
    Region = 'observations.region'
    Sources = 'observations.Source'
    Field_Report_Type = 'activity.eventtype'

    MODEL_REF_CHOICES = [
        (Field_Reports, "Field Reports"),
        (Field_Report_Type, "Field Report Type"),
        (Maps, "Maps"),
        (Region, "Region"),
        (Sources, "Sources"),
        (User, "User"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    model = models.CharField(
        max_length=50, choices=MODEL_REF_CHOICES, default=Field_Reports)
    field = models.CharField(max_length=40)
    value = models.CharField(max_length=100, blank=True)
    display = models.CharField(max_length=100, blank=True)
    icon = models.CharField(max_length=100, blank=True, null=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    sub_choice_of = models.ManyToManyField('self', blank=True,
                                           symmetrical=False)

    objects = ChoiceQuerySet.as_manager()
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        unique_together = (('model', 'field', 'value'),)

    def __str__(self):
        return ', '.join((self.model, self.field, self.value, self.display))

    @property
    def icon_id(self):
        return self.icon if self.icon else self.value

    @staticmethod
    def image_basename(choice_value):
        color = 'black'
        return '{0}-{1}'.format(choice_value, color)

    @staticmethod
    def generate_image_keys(choice_value):
        yield choice_value

    @staticmethod
    def marker_icon(choice_value, default='/static/generic-black.svg'):
        image_url = static_image_finder.get_marker_icon(
            Choice.generate_image_keys(choice_value))
        return image_url or default


class DisableChoice(Choice):
    class Meta:
        proxy = True
        verbose_name = 'Disabled Choice'


class ChoiceCharField(models.CharField):
    """Choices are stored in a Choice database table."""
    _return_empty_choices = False

    def __init__(self, *args, **kwargs):
        self._choices = (('', ''),)
        self.filter_field = kwargs.pop('filter_field', None)
        super().__init__(*args, **kwargs)
        self._choices = lazy(self.get_choices, list)()

    @property
    def choices(self):
        if not hasattr(self, 'model') or self._return_empty_choices:
            return []
        try:
            return self._choices
        except AttributeError:
            pass
        return []

    @choices.setter
    def choices(self, value):
        self._choices = value

    def contribute_to_class(self, *args, **kwargs):
        self._return_empty_choices = True
        super().contribute_to_class(*args, **kwargs)
        self._return_empty_choices = False
        setattr(
            self.model,
            f"get_{self.name}_display",
            partialmethod(self.model._get_FIELD_display, field=self),
        )

    def deconstruct(self):
        self._return_empty_choices = True
        result = super().deconstruct()
        self._return_empty_choices = False
        return result

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        errors.extend(self._check_filter_field_attribute(**kwargs))
        return errors

    def _check_choices(self):
        # override to avoid validation of DB data
        return []

    def _check_filter_field_attribute(self, **kwargs):
        if self.filter_field is not None and not isinstance(self.filter_field,
                                                            models.Field):
            return [
                checks.Error(
                    "'filter_field' must be a model Field type.",
                    hint=None,
                    obj=self,
                    id='fields.E121',
                )
            ]
        else:
            return []

    def get_choices(self, include_blank=True, blank_choice=BLANK_CHOICE_DASH,
                    limit_choices_to=None):
        """Returns choices with a default blank choices included, for use
        as SelectField choices for this field."""
        blank_defined = False
        model_name = self.model._meta.label_lower
        _choices = Choice.objects.get_choices(model_name, self.name)
        if limit_choices_to:
            _choices = _choices.filter(limit_choices_to)

        if limit_choices_to or not self.filter_field:
            choices = _choices.get_values()

            for choice, __ in choices:
                if choice in ('', None):
                    blank_defined = True
                    break
        else:
            choices = {}
            for choice in _choices:
                if choice.value in ('', None):
                    blank_defined = True
                    break
                group_values = choice.sub_choice_of.all()
                group_value = group_values[0].value if group_values else ''
                choices.setdefault(group_value, []).append(
                    (choice.value, choice.display))
            choices = [(k, v) for k, v in choices.items()]

        first_choice = (blank_choice if include_blank and
                        not blank_defined else [])
        return first_choice + list(choices)

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        # validate against our filtered choices list
        if self.filter_field and self.choices and value not in self.empty_values:
            filter_value = getattr(model_instance, self.filter_field.name)
            q = Choice.objects.get_filtered_q(
                self.filter_field.model._meta.label_lower,
                self.filter_field.name,
                filter_value)
            for option_key, option_value in self.get_choices(limit_choices_to=q):
                if isinstance(option_value, (list, tuple)):
                    # This is an optgroup, so look inside the group for
                    # options.
                    for optgroup_key, optgroup_value in option_value:
                        if value == optgroup_key:
                            return
                elif value == option_key:
                    return
            raise exceptions.ValidationError(
                self.error_messages['invalid_choice'],
                code='invalid_choice',
                params={'value': value},
            )


class ChoiceModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class SectionArea(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class Station(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class FenceLocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class FenceDamage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Fence Damage')
        verbose_name_plural = _('Fence Damage')


class KeySpecies(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Key Species')
        verbose_name_plural = _('Key Species')


class Species(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Species')
        verbose_name_plural = _('Species')


class AnimalSex(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Animal Sex')
        verbose_name_plural = _('Animal Sexes')


class AnimalAge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class CarcassAge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class TrophyStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Trophy Status')
        verbose_name_plural = _('Trophy Statuses')


class CauseOfDeath(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Cause of Death')
        verbose_name_plural = _('Causes of Death')


class InjuryCause(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class InjuryType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class FireStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Fire Status')
        verbose_name_plural = _('Fire Statuses')


class FireCause(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class Direction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class Crops(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Crops')
        verbose_name_plural = _('Crops')


class TypeOfIllegalActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Type of Illegal Activity')
        verbose_name_plural = _('Type of Illegal Activities')


class SnareAge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class SnareStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Snare Status')
        verbose_name_plural = _('Snare Statuses')


class PoacherCampAge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class TypeOfShots(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Type of Shots')
        verbose_name_plural = _('Type of Shots')


class TypeOfTrophy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Type of Trophy')
        verbose_name_plural = _('Type of Trophies')


class VehicleTypes(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Vehicle Types')
        verbose_name_plural = _('Vehicle Types')


class WeaponTypes(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Types of Weapons')
        verbose_name_plural = _('Types of Weapons')


class TrafficType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class TrafficActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Traffic Activity')
        verbose_name_plural = _('Traffic Activities')


class AccidentType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class CriticalSightingType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class TracksType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Track Type')
        verbose_name_plural = _('Track Types')


class VehicleType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class MedicalEquipmentRequired(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Medical Equipment Required')
        verbose_name_plural = _('Medical Equipment Required')


class MedicalEvacSecurity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Medical Evac Security')
        verbose_name_plural = _('Medical Evac Securities')


class DetectionType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class ActionTaken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Action Taken')
        verbose_name_plural = _('Actions Taken')


class Conservancy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Conservancy')
        verbose_name_plural = _('Conservancies')


class Behavior(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class Color(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class Health(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Health')
        verbose_name_plural = _('Health')


class FenceSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class PoachingMean(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class Tribe(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class IllegalActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Illegal Activity')
        verbose_name_plural = _('Illegal Activities')


class Livestock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Livestock')
        verbose_name_plural = _('Livestock')


class ContactType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class WildlifeGap(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)


class IncidentStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Incident Status')
        verbose_name_plural = _('Incident Statuses')


class Nationality(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Nationality')
        verbose_name_plural = _('Nationalities')


class Village(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Village')
        verbose_name_plural = _('Villages')


class ArrestViolation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Arrest Violation')
        verbose_name_plural = _('Arrest Violations')


# Liwonde specific tables
class AnimalCondition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Animal Condition')
        verbose_name_plural = _('Animal Conditions')


class ArrestNationality(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Arrest Nationality')
        verbose_name_plural = _('Arrest Nationalities')


class ReasonForArrest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Reason for Arrest')
        verbose_name_plural = _('Reasons for Arrest')


class ArrestVillageName(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Arrest Village Name')
        verbose_name_plural = _('Arrest Village Names')


class SpoorAge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('SPOOR Age')
        verbose_name_plural = _('SPOOR Ages')


class SpoorFootType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('SPOOR Foot Type')
        verbose_name_plural = _('SPOOR Foot Types')


class SnareAction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    ordernum = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _('Snare Action')
        verbose_name_plural = _('Snare Actions')
