from django.contrib.gis.db import models
from django.contrib.auth.models import User
from treebeard.al_tree import AL_Node, AL_NodeManager


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditableModel(TimestampedModel):
    user = models.ForeignKey(to=User)

    class Meta:
        abstract = True


class HierarchyManager(AL_NodeManager):
    pass


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
