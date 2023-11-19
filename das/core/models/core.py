import uuid

from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin
from django_multitenant.models import TenantModel

from django.conf import settings
from django.contrib.gis.db import models
from django.core.cache import cache

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


class DASTenant(TenantModel):
    id = models.UUIDField(primary_key=True)
    domain = models.CharField(max_length=100)
    tenant_id = "id"

    def __str__(self):
        return self.domain


class HierarchyManager(TenantManagerMixin, models.Manager):
    def get_ancestors(self, child, ancestors=None):
        ancestors = set() if not ancestors else ancestors
        if child not in ancestors:
            ancestors.add(child)
            for parent in child.parents():
                if parent not in ancestors:
                    yield parent
                    for gparent in self.get_ancestors(parent, ancestors):
                        if gparent not in ancestors:
                            yield gparent

    def get_descendants(self, node, children=None):
        children = set() if not children else children
        if node not in children:
            children.add(node)
            for f in node.children.all():
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
