import uuid
import logging
import copy

import simplejson as json
from django.core import serializers
from django.conf import settings
import django.db.transaction as transaction
from django.contrib.auth import get_user_model
from django.contrib.gis.db import models
from django.contrib.gis.geos import Polygon
import django.utils
from django.contrib.postgres.fields import JSONField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from core.models import TimestampedModel
from observations.models import Subject


logger = logging.getLogger(__name__)


class RevisionManager(models.Manager):
    def __init__(self, model, instance = None, ):
        super().__init__()
        self.model = model
        self.instance = instance

    def get_queryset(self):
        if self.instance is None:
            return super(RevisionManager, self).get_queryset()

        f = {'object_id': self.instance.pk}
        return super(RevisionManager, self).get_queryset().filter(**f)\
            .order_by('sequence')


class RevisionDescriptor(object):
    def __init__(self, model, manager_class, manager_name):
        self.model = model
        self.manager_class = manager_class
        self.manager_name = manager_name

    def __get__(self, instance, owner):
        if instance is None:
            return self.manager_class(self.model)
        return self.manager_class(self.model, instance)


class UserField(models.ForeignKey):
    def __init__(self, to = getattr(settings, 'AUTH_USER_MODEL', 'auth.User'), null = True, editable = False,  **kwargs):
        super().__init__(to = to, null = null, editable = editable, **kwargs)

    def contribute_to_class(self, cls, name):
        super().contribute_to_class(cls, name)


def make_revision_model_name(model):
    return '{0}Revision'.format(model._meta.object_name)


def get_revision_model(model):
    return ContentType.objects.get_by_natural_key(
        model._meta.app_label,
        make_revision_model_name(model).lower()
    )


class RevisionAdapter(object):
    fields = ()
    exclude = []

    def __init__(self, model):
        self.model = model
        self.ignore_fields = getattr(model,
                                     'revision_ignore_fields', [])

    def get_fieldnames(self):
        opts = self.model._meta.concrete_model._meta
        fields = self.fields or (field.name for field in opts.local_fields
                                 + opts.local_many_to_many)
        fields = (opts.get_field(field) for field in fields
                  if not field in self.exclude)
        for field in fields:
            if field.remote_field:
                yield field.name
            else:
                yield field.attname

    def _serialize(self, obj, fieldnames):
        data = serializers.serialize(
            'json',
            (obj,),
            fields=fieldnames
        )
        data = json.loads(data)[0]
        data = data['fields']
        return data

    def get_data_copy(self, obj):
        return {k: copy.deepcopy(getattr(obj, k)) for
                k in list(self.get_fieldnames())}

    def get_serialized_data(self, obj):
        return self._serialize(obj, list(self.get_fieldnames()))

    def get_serialized_data_diff(self, obj, original):
        fields = list(self.get_fieldnames())
        fields_diff = [key for key in fields if original.get(key, None) != getattr(obj, key)]
        if fields_diff:
            if not set(fields_diff) ^ set(self.ignore_fields):
                return None
        return self._serialize(obj, fields_diff)


AC_ADDED = 'added'
AC_UPDATED = 'updated'
AC_DELETED = 'deleted'

ACTION_CHOICES = (
    (AC_ADDED, 'Added'),
    (AC_UPDATED, 'Updated'),
    (AC_DELETED, 'Deleted'),
)


class Revision(object):
    manager_class = RevisionManager

    def contribute_to_class(self, cls, name):
        self.manager_name = name
        models.signals.class_prepared.connect(self.finalize, sender=cls)

    def create_revision(self, instance, action):
        user = getattr(instance, 'revision_user', None)
        manager = getattr(instance, self.manager_name)
        adapter = RevisionAdapter(type(instance))

        sequence = instance.revision_sequence + 1

        if sequence == 1:
            data = adapter.get_serialized_data(instance)
        elif action == AC_DELETED:
            data = {}
        else:
            data = adapter.get_serialized_data_diff(instance,
                                                    instance.revision_original)
            if not data:
                return

        manager.create(
            object_id=instance.id,
            sequence=sequence,
            action=action,
            user=user,
            data=data
        )

    def post_save(self, instance, created, **kwargs):
        try:
            self.create_revision(instance, created and AC_ADDED or AC_UPDATED)
        except Exception as ex:
            logger.exception(ex)

    def post_delete(self, instance, **kwargs):
        self.create_revision(instance, AC_DELETED)

    def post_init(self, instance, **kwargs):
        manager = getattr(instance, self.manager_name)
        instance.revision_sequence = 0
        if instance.id:
            adapter = RevisionAdapter(type(instance))
            instance.revision_original = adapter.get_data_copy(instance)
            sequences = manager.all().filter(
                object_id=instance.id)
            sequences = sequences.order_by('-sequence')
            for sequence in sequences.values('sequence'):
                instance.revision_sequence = sequence['sequence']
                break

    def finalize(self, sender, **kwargs):
        revision_model = self.create_revision_model(sender)

        models.signals.post_save.connect(self.post_save, sender = sender, weak = False)
        models.signals.post_delete.connect(self.post_delete, sender = sender, weak = False)
        models.signals.post_init.connect(self.post_init, sender=sender, weak=False)

        descriptor = RevisionDescriptor(revision_model, self.manager_class, self.manager_name)
        setattr(sender, self.manager_name, descriptor)

    def get_table_fields(self, model):
        rel_name = '_%s_revision'%model._meta.object_name.lower()


        def to_str(instance):
            result = '%s: %s %s at %s'%(model._meta.object_name,
                                            instance.object_id,
                                            instance.get_action_display().lower(),
                                            instance.revision_at,
                                                )
            return result

        user_field = UserField(related_name = rel_name, editable = False,
                               on_delete=models.SET_NULL)

        #check if this manager has been attached to auth user model
        if [model._meta.app_label, model.__name__] == getattr(settings, 'AUTH_USER_MODEL', 'auth.User').split("."):
            user_field = UserField(related_name = rel_name, editable = False, to = 'self')

        return {
            'id': models.UUIDField(primary_key=True, default=uuid.uuid4),
            'object_id': models.UUIDField(),
            'action': models.CharField(max_length=10, choices=ACTION_CHOICES,
                                          default=AC_ADDED),
            'revision_at': models.DateTimeField(auto_now_add=True),
            'sequence': models.IntegerField(help_text='Revision sequence'),
            'user': user_field,
            'data': JSONField(default={}),
            '__str__': to_str,
            '__module__': model.__module__,
        }

    def get_meta_options(self, model):
        result = {
            'unique_together': ('object_id', 'sequence',),
            'app_label': model._meta.app_label,
        }
        from django.db.models.options import DEFAULT_NAMES
        if 'default_permissions' in DEFAULT_NAMES:
            result.update({'default_permissions': ()})
        return result

    def create_revision_model(self, model):
        attrs = self.get_table_fields(model)
        attrs.update(Meta = type(str('Meta'), (), self.get_meta_options(model)))
        name = make_revision_model_name(model)
        return type(name, (models.Model,), attrs)


class RevisionMixin(object):
    def save(self, *args, **kwargs):
        with transaction.atomic():
            return super().save(*args, **kwargs)