import uuid
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from django.contrib.gis.db import models

from treebeard.al_tree import AL_Node


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditableModel(TimestampedModel):
    user = models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class HierarchyManager(models.Manager):
    def get_ancestors(self, child):
        for parent in child.parents():
            yield parent
            for gparent in self.get_ancestors(parent):
                yield gparent

    def get_descendants(self, node):
        for f in node.children.all():
            yield f
            for gchild in self.get_descendants(f):
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


class HierarchyModel(models.Model):
    """
    Provides a recursive hierarchy on self.
    A child can have multiple parents.
    These access functions are used by other recursive Mixins.
    """
    class Meta:
        abstract = True

    objects = HierarchyManager()

    children = models.ManyToManyField('self', blank=True,
                                      symmetrical=False,
                                      related_name='_parents',
                                      )

    def parents(self):
        return self.__class__.objects.filter(children=self)

    def get_ancestors(self):
        return self.__class__.objects.get_ancestors(self)

    def get_descendants(self):
        return self.__class__.objects.get_descendants(self)

    def get_ancestor_ids(self):
        return [a.id for a in self.get_ancestors()]


class QueryHistory(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    pid = models.IntegerField('The OS process id', null=False, blank=False)
    elapsed = DurationField(null=False, blank=False)
    wait_event = models.CharField(max_length=100, null=True, blank=True)
    cpu_percent = models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True)
    mem_percent = models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True)
    query = models.TextField(db_index=True)
    digest = models.CharField("The sha1 digest of the query field", max_length=512, db_index=True)

    class Meta:
        verbose_name = _('query history')
        verbose_name_plural = _('query histories')
        index_together = [('pid', 'digest', 'updated_at')]

    def __str__(self):
        return self.query
