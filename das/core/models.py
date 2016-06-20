import uuid

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import checks, exceptions, validators
from django.db.models.fields import BLANK_CHOICE_DASH
import django.db.utils
from django.utils.encoding import smart_text
from django.contrib.gis.db import models
from django.utils.functional import lazy, curry, Promise, cached_property
from treebeard.al_tree import AL_Node, AL_NodeManager


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditableModel(TimestampedModel):
    user = models.ForeignKey(to=settings.AUTH_USER_MODEL)

    class Meta:
        abstract = True


class HierarchyManager(AL_NodeManager):
    def get_decendants(self, qs):
        """
        Returns all nodes AND descendant nodes for the list of nodes
        found in qs.
        TODO: Optimize this for Postgresql using a CTE common table expression
        """
        raise NotImplementedError()
        direct_nodes = self.permission_sets.all()
        all_nodes = set()

        for ps in direct_nodes:
            all_nodes.add(ps)
            ancestors = ps.get_ancestors()
            for ancestor in ancestors:
                all_nodes.add(ancestor)
        return all_nodes


class HierarchyModel(AL_Node):
    """
    Establish an adjacency list for a table and provide some access functions.
    These access functions are user by other Hierarchy Mixins.
    """
    class Meta:
        abstract = True

    node_order_by = ['name']
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')

    def get_ancestor_ids(self):
        return [a.id for a in self.get_ancestors()]


class ChoicesManager(models.Manager):
    def get_choices_for_field(self, model, field):
        result = self.filter(model=model, field=field)
        return result.values_list('value', 'display')

    def get_choices(self, model, field):
        return self.filter(model=model, field=field)

    def get_values(self):
        return self.values_list('value', 'display')

    def get_filtered_choices(self, parent_model, parent_field, parent_value):
        """after calling get_choices(), filter choices by parent values"""
        parent = self.all().get_choices(parent_model, parent_field).filter(value=parent_value)
        return self.filter(sub_choice_of=parent)


class Choices(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    model = models.CharField(max_length=50)
    field = models.CharField(max_length=40)
    value = models.CharField(max_length=40, blank=True)
    display = models.CharField(max_length=100, blank=True)
    sub_choice_of = models.ManyToManyField('self', blank=True,
                                           symmetrical=False)

    objects = ChoicesManager()
    class Meta:
        unique_together = (('model', 'field', 'value'),)


class ChoicesCharField(models.CharField):
    """Choices are stored in a Choices database table."""
    _return_empty_choices = False

    def __init__(self, *args, **kwargs):
        self._choices = (('', ''),)
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
        setattr(self.model, 'get_%s_display' % self.name,
                curry(self.model._get_FIELD_display, field=self))

    def deconstruct(self):
        self._return_empty_choices = True
        result = super().deconstruct()
        self._return_empty_choices = False
        return result

    def _check_choices(self):
        #override to avoid validation of DB data
        return []

    def get_choices(self, include_blank=True, blank_choice=BLANK_CHOICE_DASH,
                    limit_choices_to=None):
        """Returns choices with a default blank choices included, for use
        as SelectField choices for this field."""
        blank_defined = False
        choices = Choices.objects.get_choices_for_field(self.model._meta.label_lower,
                                                        self.name)
        for choice, __ in choices:
            if choice in ('', None):
                blank_defined = True
                break

        first_choice = (blank_choice if include_blank and
                                        not blank_defined else [])
        return first_choice + list(choices)



class FilterChoicesCharField(ChoicesCharField):
    def __init__(self, *args, **kwargs):
        self.filter_field = kwargs.pop('filter_field', None)
        super().__init__(*args, **kwargs)

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        errors.extend(self._check_filter_field_attribute(**kwargs))
        return errors

    def _check_filter_field_attribute(self, **kwargs):
        if self.filter_field is None:
            return [
                checks.Error(
                    "FilterChoicesCharFields must define a 'filter_field' attribute.",
                    hint=None,
                    obj=self,
                    id='fields.E120',
                )
            ]
        elif not isinstance(self.filter_field,
                            str) or not self.filter_field:
            return [
                checks.Error(
                    "'filter_field' must be a non-empty string.",
                    hint=None,
                    obj=self,
                    id='fields.E121',
                )
            ]
        else:
            return []

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        # validate against our filtered choices list
        if self.choices and value not in self.empty_values:
            for option_key, option_value in self.choices:
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
