import re
import uuid
from functools import partialmethod

from django_multitenant.fields import TenantForeignKey
from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin

from django.contrib.gis.db import models
from django.core import checks, exceptions
from django.db.models import Index, UniqueConstraint
from django.db.models.fields import BLANK_CHOICE_DASH
from django.utils import timezone
from django.utils.functional import lazy

from core.models import DASTenant, UUIDModel
from core.utils import static_image_finder
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager


class ChoiceQuerySet(models.QuerySet):
    def get_choices_for_field(self, model, field):
        result = self.get_choices(model, field)
        return result.get_values()

    def get_choices(self, model, field):
        return self.filter(model=model, field=field).order_by("ordernum")

    def get_values(self):
        return self.values_list("value", "display")

    def get_filtered_q(self, parent_model, parent_field, parent_value):
        parent = self.all().get_choices(parent_model, parent_field).filter(value=parent_value)
        return models.Q(sub_choice_of=parent)

    def get_filtered_choices(self, parent_model, parent_field, parent_value):
        """after calling get_choices(), filter choices by parent values"""
        parent = self.all().get_choices(parent_model, parent_field).filter(value=parent_value)
        return self.filter(sub_choice_of=parent)

    def filter_active_choices(self):
        return self.filter(is_active=True)

    def filter_inactive_choices(self):
        return self.filter(is_active=False)

    def disable_choices(self):
        return self.update(delete_on=timezone.now(), is_active=False)

    def soft_delete(self):
        return self.disable_choices()


class DynamicChoice(TenantModelMixin, UUIDModel):
    choice_name = models.CharField(max_length=100, blank=True, null=False, verbose_name="Choice name")
    model_name = models.CharField(max_length=100, verbose_name="Model lookup")
    criteria = models.CharField(max_length=100, verbose_name="Criteria")
    value_col = models.CharField(max_length=100, verbose_name="Value column")
    display_col = models.CharField(max_length=100, verbose_name="Display column")
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "choice_name"],
                name="%(app_label)s_%(class)s_unique_choice_name_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "choice_name"], name="%(class)s_choice_name_idx")]


class SoftDeleteModelManager(TenantManagerMixin, models.Manager):
    pass


class SoftDeleteModel(TenantModelMixin, models.Model):
    delete_on = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="%(app_label)s_%(class)s",
    )

    tenant_id = "das_tenant_id"
    objects = SoftDeleteModelManager()

    class Meta:
        abstract = True

    def disable(self):
        self.delete_on = timezone.now()
        self.is_active = False
        self.save()


class ChoiceManager(TenantManagerMixin, models.Manager.from_queryset(ChoiceQuerySet)):
    use_in_migrations = True


class Choice(SoftDeleteModel):
    VALID_VALUE_CHARS = r"^\w+$"
    VALID_FIELD_CHARS = r"^\w+$"
    EVENT_MODEL = "activity.event"
    EVENT_TYPE_MODEL = "activity.eventtype"
    USER_MODEL = "accounts.user.User"
    MAPS_MODEL = "mapping.TileLayer"
    OBSERVATION_REGION_MODEL = "observations.region"
    OBSERVATION_SOURCE_MODEL = "observations.Source"

    MODEL_REF_CHOICES = [
        (EVENT_MODEL, "Event"),
        (EVENT_TYPE_MODEL, "Event Type"),
        (USER_MODEL, "User"),
        (MAPS_MODEL, "Maps"),
        (OBSERVATION_REGION_MODEL, "Region"),
        (OBSERVATION_SOURCE_MODEL, "Sources"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    model = models.CharField(max_length=50, choices=MODEL_REF_CHOICES, default=EVENT_MODEL)
    field = models.CharField(max_length=40)
    value = models.CharField(max_length=100, blank=True)
    display = models.CharField(max_length=100, blank=True)
    icon = models.CharField(max_length=100, blank=True, null=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    sub_choice_of = models.ManyToManyField("self", blank=True, symmetrical=False, through="choices.SubChoiceOf")
    updated_at = models.DateTimeField(auto_now=True, null=True)

    objects = ChoiceManager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "model", "field", "value"], name="%(app_label)s_%(class)s_tenant_model_unique"
            ),
        ]

    def __str__(self):
        return ", ".join((self.model, self.field, self.value, self.display))

    def clean(self):
        """
        Validate that field and value are required and contain only unicode word characters
        (letters, numbers, underscores) - no spaces.
        Only validates new instances (pk is None) for backward compatibility.
        """

        errors = {}
        fields_to_validate = [
            ("field", "Field"),
            ("value", "Value"),
        ]

        for field_name, field_label in fields_to_validate:
            field_value = getattr(self, field_name, None)
            if not field_value:
                errors[field_name] = f"{field_label} is required and cannot be empty."
            elif not re.match(getattr(Choice, f"VALID_{field_name.upper()}_CHARS"), field_value):
                errors[field_name] = (
                    f"{field_label} must contain only letters, numbers, and underscores (no spaces). "
                    f"Got: '{field_value}'"
                )

        if errors:
            raise exceptions.ValidationError(errors)

    @property
    def icon_id(self):
        return self.icon if self.icon else self.value

    @staticmethod
    def image_basename(choice_value):
        color = "black"
        return f"{choice_value}-{color}"
        return "{0}-{1}".format(choice_value, color)

    @staticmethod
    def generate_image_keys(choice_value):
        yield choice_value

    @staticmethod
    def marker_icon(choice_value, default="/static/generic-black.svg"):
        image_url = static_image_finder.get_marker_icon(Choice.generate_image_keys(choice_value))
        return image_url or default


class SubChoiceOf(TenantModelMixin, UUIDModel):
    from_choice = TenantForeignKey(
        default=uuid.uuid4, on_delete=models.CASCADE, related_name="from_choice", to="choices.choice"
    )
    to_choice = TenantForeignKey(
        default=uuid.uuid4, on_delete=models.CASCADE, related_name="to_choice", to="choices.choice"
    )
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="%(app_label)s_%(class)s",
    )

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "from_choice_id", "to_choice_id"],
                name="%(app_label)s_%(class)s_unique_across_tenants",
            ),
        ]
        indexes = [
            Index(
                fields=["das_tenant", "from_choice"],
            ),
            Index(
                fields=["das_tenant", "to_choice"],
            ),
        ]


class DisableChoice(Choice):
    class Meta:
        proxy = True
        verbose_name = "Disabled Choice"


class ChoiceCharField(models.CharField):
    """Choices are stored in a Choice database table."""

    _return_empty_choices = False

    def __init__(self, *args, **kwargs):
        self._choices = (("", ""),)
        self.filter_field = kwargs.pop("filter_field", None)
        super().__init__(*args, **kwargs)
        self._choices = lazy(self.get_choices, list)()

    @property
    def choices(self):
        if not hasattr(self, "model") or self._return_empty_choices:
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
        if self.filter_field is not None and not isinstance(self.filter_field, models.Field):
            return [
                checks.Error(
                    "'filter_field' must be a model Field type.",
                    hint=None,
                    obj=self,
                    id="fields.E121",
                )
            ]
        else:
            return []

    def get_choices(self, include_blank=True, blank_choice=BLANK_CHOICE_DASH, limit_choices_to=None):
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
                if choice in ("", None):
                    blank_defined = True
                    break
        else:
            choices = {}
            for choice in _choices:
                if choice.value in ("", None):
                    blank_defined = True
                    break
                group_values = choice.sub_choice_of.all()
                group_value = group_values[0].value if group_values else ""
                choices.setdefault(group_value, []).append((choice.value, choice.display))
            choices = [(k, v) for k, v in choices.items()]

        first_choice = blank_choice if include_blank and not blank_defined else []
        return first_choice + list(choices)

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        # validate against our filtered choices list
        if self.filter_field and self.choices and value not in self.empty_values:
            filter_value = getattr(model_instance, self.filter_field.name)
            q = Choice.objects.get_filtered_q(
                self.filter_field.model._meta.label_lower, self.filter_field.name, filter_value
            )
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
                self.error_messages["invalid_choice"],
                code="invalid_choice",
                params={"value": value},
            )
