import uuid

import django.db.models.fields.related
from django.conf import settings
from django.contrib.gis.db import models
from django.core.cache import cache
from django.db.models.fields.related import (
    lazy_related_operation,
    make_model_tuple,
    resolve_relation,
)
from django_multitenant.fields import TenantForeignKey
from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin
from django_multitenant.models import TenantManager, TenantModel
from utils.migrations.columns import default_tenant_id


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)

    class Meta:
        abstract = True


class AuditableModel(TimestampedModel):
    user = models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class DASTenantManager(TenantManager):
    def get_origin(self):
        """get the DASTenant origin tenant. The origin is the first tenant and was created with migrations

        Returns:
            DASTenent: the origin tenant

        """
        return self.get(domain=settings.SERVER_FQDN)


class DASTenant(TenantModel):
    id = models.UUIDField(primary_key=True)
    domain = models.CharField(max_length=100)
    tenant_id = "id"
    objects = DASTenantManager()

    def __str__(self):
        return self.domain


class TenantManyToManyField(models.ManyToManyField):
    """This version of ManyToManyField is used to create a tenant aware intermediary model (through model) for the many to many relationship.
    The intermediary model is created directly in the database, and as such we don't see these commands in the migration.
    Because of this, it's harder to then use this in place of existing ManyToManyField implementations.
    If we do need to create a tenant aware many to many relationship that is a net new use, then we can use this field.

    The key piece is to replace the original create_many_to_many_intermediary_model with the tenant version.

    Until then, the pieces need for this class to work have been disabled, specifically the monkeypatch to django.db.models.fields.related.create_many_to_many_intermediary_model

    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "TenantManyToManyField is not implemented yet. Requires removing this and activating the original_create_many_to_many_intermediary_model monkeypatch"
        )
        super().__init__(*args, **kwargs)


original_create_many_to_many_intermediary_model = django.db.models.fields.related.create_many_to_many_intermediary_model


def create_tenant_many_to_many_intermediary_model(field, klass):
    if not isinstance(field, TenantManyToManyField):
        return original_create_many_to_many_intermediary_model(field, klass)

    def set_managed(model, related, through):
        through._meta.managed = model._meta.managed or related._meta.managed

    to_model = resolve_relation(klass, field.remote_field.model)
    to_object_name = to_model.split(".")[-1] if isinstance(to_model, str) else to_model._meta.object_name

    to = make_model_tuple(to_model)[1]
    from_ = klass._meta.model_name
    if to == from_:
        to = "to_%s" % to
        from_ = "from_%s" % from_

    class_name = "%s%s" % (klass._meta.object_name, to_object_name)
    name = "%s%s" % (from_, to)
    lazy_related_operation(set_managed, klass, to_model, name)

    manager_name = "%sManager" % class_name
    manager = type(
        manager_name,
        (TenantManagerMixin, models.Manager),
        {
            "use_in_migrations": True,
            "get_by_natural_key": lambda self, from_id, to_id: self.get(**{from_: from_id, to: to_id}),
        },
    )

    meta = type(
        "Meta",
        (),
        {
            "db_table": "%s_%s" % (klass._meta.app_label, name),
            "auto_created": klass,
            "app_label": klass._meta.app_label,
            "db_tablespace": klass._meta.db_tablespace,
            "unique_together": ("das_tenant", from_, to),
            "apps": field.model._meta.apps,
            "base_manager_name": "objects",
            "default_manager_name": "objects",
        },
    )

    def natural_key(self):
        return (getattr(self, from_), getattr(self, to))

    # Construct and return the new class.
    return type(
        class_name,
        (
            TenantModelMixin,
            UUIDModel,
        ),
        {
            "Meta": meta,
            "__module__": klass.__module__,
            from_: TenantForeignKey(
                klass,
                db_tablespace=field.db_tablespace,
                db_constraint=field.remote_field.db_constraint,
                on_delete=models.CASCADE,
            ),
            to: TenantForeignKey(
                to_model,
                db_tablespace=field.db_tablespace,
                db_constraint=field.remote_field.db_constraint,
                on_delete=models.CASCADE,
            ),
            "das_tenant": models.ForeignKey(
                DASTenant,
                on_delete=models.CASCADE,
                default=default_tenant_id,
                related_name="%s_%s" % (klass._meta.app_label, name),
            ),
            "tenant_id": "das_tenant_id",
            "objects": manager(),
            "natural_key": natural_key,
        },
    )


# This is a monkeypatch to replace the original create_many_to_many_intermediary_model with the tenant version
# Deactivated for now. Requires testing
# django.db.models.fields.related.create_many_to_many_intermediary_model = create_tenant_many_to_many_intermediary_model


class HierarchyManager(TenantManagerMixin, models.Manager):
    def get_ancestors(self, child):
        ancestors = set()
        queue = [child]

        while queue:
            current = queue.pop(0)
            if current not in ancestors:
                ancestors.add(current)
                parents = current.parents()
                for parent in parents:
                    if parent not in ancestors:
                        queue.append(parent)
                        yield parent

    def get_descendants(self, node, children=None):
        children = set() if not children else children
        if node not in children:
            children.add(node)
            for f in node.children.prefetch_related("children").all():
                if f not in children:
                    yield f
                    for gchild in self.get_descendants(f, children):
                        if gchild not in children:
                            yield gchild


class HierarchQuerySet(models.QuerySet):
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


class HierarchyModel(TenantModelMixin, models.Model):
    """
    Provides a recursive hierarchy on self.
    A child can have multiple parents.
    These access functions are used by other recursive Mixins.
    """

    class Meta:
        abstract = True

    objects = HierarchyManager()
    children = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="_parents",
    )
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"

    def parents(self):
        return self.__class__.objects.filter(children=self)

    def get_ancestors(self):
        return self.__class__.objects.get_ancestors(self)

    def get_descendants(self):
        return self.__class__.objects.get_descendants(self)

    def get_ancestor_ids(self):
        return [a.id for a in self.get_ancestors()]


class TenantSingletonModel(TenantModelMixin, UUIDModel):
    instance_id = None

    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"

    class Meta:
        abstract = True
        base_manager_name = "objects"
        default_manager_name = "objects"

    def set_cache(self):
        cache.set(self.__class__.__name__, self)

    def save(self, *args, **kwargs):
        self.pk = self.instance_id
        super(TenantSingletonModel, self).save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        pass

    @classmethod
    def get_instance(cls, **kwargs):
        o, created = cls.objects.get_or_create(pk=cls.instance_id, **kwargs)
        return o
