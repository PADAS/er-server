import uuid

import logging

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField

from das_server import pubsub
from observations.models import Source
from core.models import TimestampedModel
from tracking.models.plugin_base import DasDefaultTarget

logger = logging.getLogger(__name__)

class SourcePluginResult(object):
    count=0
    plugin_type=None
    source_id=None

    def to_dict(self):
        """ returns a dict of attributes of this object """
        return {
            'count': self.count,
            'plugin_type': self.plugin_type,
            'source_id': self.source_id
        }



class SourcePlugin(TimestampedModel):
    """
    Maps Plugin parameters to Source
    """
    STATUS_ENABLED = 'enabled'
    STATUS_DISABLED = 'disabled'

    STATUS_CHOICES = (STATUS_ENABLED, 'Enabled',
                      STATUS_DISABLED, 'Disabled'
                      )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    limits = models.Q(app_label='tracking', model='savannahplugin')

    # Generic foreign key to plugin
    plugin_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=limits)
    plugin_id = models.UUIDField()
    plugin = GenericForeignKey('plugin_type', 'plugin_id')

    source = models.ForeignKey(Source, on_delete=models.CASCADE,
                              related_name='source_plugins',
                              related_query_name='source_plugin')

    cursor_data = JSONField(null=True)

    status = models.CharField(max_length=15, default=STATUS_ENABLED)

    def execute(self, target=None):
        '''
        Run basic logic to fetch new observations for the associated source.
        :return:
        '''
        target = target or DasDefaultTarget()

        result = SourcePluginResult()
        result.plugin_type = self.plugin_type
        result.source_id = self.source_id

        with target:

            cnt=0
            for x in self.plugin.fetch(self):
                target.send(x)
                cnt=cnt+1

            result.count=cnt

        return result

    def maintenance(self, target=None):
        raise NotImplementedError('maintenance is not yet implemented')


