from django.conf import settings
from django.contrib.gis.db import models
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


