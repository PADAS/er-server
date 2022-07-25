import logging
import uuid

import simplejson as json

import django.db.transaction as transaction
import django.dispatch
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.core import serializers
from django.db.models import Max

logger = logging.getLogger(__name__)

relation_deleted = django.dispatch.Signal(
    providing_args=['relation', 'instance', 'related_query_name'])


class RevisionManager(models.Manager):

    def __init__(self, model, instance=None):
        super().__init__()
        self.model = model
        self.instance = instance

    def get_queryset(self):
        if self.instance is None:
            return super(RevisionManager, self).get_queryset()

        f = {'object_id': self.instance.pk}
        queryset = super(RevisionManager, self).get_queryset().filter(**f)

        return queryset

    def all_user(self):
        """prefetch user"""
        queryset = self.select_related('user')
        return queryset


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
    def __init__(self, to=getattr(settings, 'AUTH_USER_MODEL', 'auth.User'), null=True, editable=False,  **kwargs):
        super().__init__(to=to, null=null, editable=editable, **kwargs)

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
        result = self._serialize(obj, list(self.get_fieldnames()))
        return result

    def get_serialized_data(self, obj):
        return self._serialize(obj, list(self.get_fieldnames()))

    def get_serialized_data_diff(self, obj, original):
        fields = list(self.get_fieldnames())
        obj_data = self._serialize(obj, fields)
        fields_diff = [key for key in fields if
                       original.get(key, None) != obj_data.get(key, None)]
        if fields_diff:
            if not set(fields_diff) ^ set(self.ignore_fields):
                return None
        return {k: v for k, v in obj_data.items() if k in fields_diff}


AC_ADDED = 'added'
AC_UPDATED = 'updated'
AC_DELETED = 'deleted'
AC_RELATION_DELETED = 'rel-del'

ACTION_CHOICES = (
    (AC_ADDED, 'Added'),
    (AC_UPDATED, 'Updated'),
    (AC_DELETED, 'Deleted'),
    (AC_RELATION_DELETED, 'Relation Deleted')
)


class Revision(object):
    manager_class = RevisionManager
    revision_adapter = RevisionAdapter

    def contribute_to_class(self, cls, name):
        self.manager_name = name
        models.signals.class_prepared.connect(self.finalize, sender=cls)

    def create_revision(self, instance, action, **kwargs):
        user = getattr(instance, 'revision_user', None)
        manager = getattr(instance, self.manager_name)
        adapter = self.revision_adapter(type(instance))

        instance.revision_sequence = 0
        if instance.id:
            sequences = manager.all()
            sequences = sequences.order_by('-sequence')
            for sequence in sequences.values_list('sequence', flat=True):
                instance.revision_sequence = sequence
                break

        if instance.revision_sequence == 0:
            data = adapter.get_serialized_data(instance)
        elif action == AC_DELETED:
            data = {}
        elif action == AC_RELATION_DELETED:
            relation = kwargs.get('relation')
            related_query_name = kwargs.get('related_query_name')
            relation_model = '.'.join(
                (relation._meta.app_label, relation._meta.object_name))
            # relation_name = kwargs.get('related_query_name')
            data = {'relation_id': str(
                relation.id), 'relation_model': relation_model, 'related_query_name': related_query_name}
        else:
            data = adapter.get_serialized_data_diff(instance,
                                                    instance.revision_original)
            if not data:
                return

        with transaction.atomic():

            o = manager.filter(object_id=instance.id).aggregate(
                max_sequence=Max('sequence'))
            max_sequence = o.get('max_sequence') or 0

            revision = manager.create(
                object_id=instance.id,
                sequence=max_sequence + 1,
                action=action,
                user=user,
                data=data
            )

        instance.revision_sequence = revision.sequence

    def post_save(self, instance, created, **kwargs):
        try:
            self.create_revision(instance, created and AC_ADDED or AC_UPDATED)
        except Exception as ex:
            logger.exception(ex)
            raise

    def post_delete(self, instance, **kwargs):
        self.create_revision(instance, AC_DELETED)

    def relation_deleted(self, relation, instance, **kwargs):
        self.create_revision(instance, AC_RELATION_DELETED,
                             relation=relation, **kwargs)

    def post_init(self, instance, **kwargs):
        instance.revision_sequence = 0
        if instance.id:
            adapter = RevisionAdapter(type(instance))
            instance.revision_original = adapter.get_data_copy(instance)

    def finalize(self, sender, **kwargs):
        revision_model = self.create_revision_model(sender)

        models.signals.post_save.connect(
            self.post_save, sender=sender, weak=False)
        models.signals.post_delete.connect(
            self.post_delete, sender=sender, weak=False)
        models.signals.post_init.connect(
            self.post_init, sender=sender, weak=False)
        relation_deleted.connect(
            self.relation_deleted, sender=sender, weak=False)

        descriptor = RevisionDescriptor(
            revision_model, self.manager_class, self.manager_name)
        setattr(sender, self.manager_name, descriptor)

    def get_table_fields(self, model):
        rel_name = '_%s_revision' % model._meta.object_name.lower()

        def to_str(instance):
            result = '%s: %s %s at %s' % (model._meta.object_name,
                                          instance.object_id,
                                          instance.get_action_display().lower(),
                                          instance.revision_at,
                                          )
            return result

        user_field = UserField(related_name=rel_name, editable=False,
                               on_delete=models.SET_NULL)

        # check if this manager has been attached to auth user model
        if [model._meta.app_label, model.__name__] == getattr(settings, 'AUTH_USER_MODEL', 'auth.User').split("."):
            user_field = UserField(related_name=rel_name,
                                   editable=False, to='self')

        return {
            'id': models.UUIDField(primary_key=True, default=uuid.uuid4),
            'object_id': models.UUIDField(),
            'action': models.CharField(max_length=10, choices=ACTION_CHOICES,
                                       default=AC_ADDED),
            'revision_at': models.DateTimeField(auto_now_add=True),
            'sequence': models.IntegerField(help_text='Revision sequence'),
            'user': user_field,
            'data': models.JSONField(default=dict),
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
        attrs.update(Meta=type(str('Meta'), (), self.get_meta_options(model)))
        name = make_revision_model_name(model)
        return type(name, (models.Model,), attrs)


class RevisionMixin(object):
    def save(self, *args, **kwargs):
        with transaction.atomic():
            return super().save(*args, **kwargs)
