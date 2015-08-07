from django.db import models
from django_pgjson.fields import JsonBField
import uuid

class PluginConfManager(models.Manager):
    pass

class PluginConf(models.Model):

    objects = PluginConfManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    plugin_name = models.CharField('plugin name', max_length=100, null=True)
    created_at = models.DateTimeField('created at', null=True)
    configuration = JsonBField()


class PluginConfSourceManager(models.Manager):
    pass

class PluginConfSource(models.Model):
    objects = PluginConfSourceManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    plugin_conf = models.ForeignKey('data_input.PluginConf', null=True)
    source = models.ForeignKey('observations.Source')
    additional = JsonBField()

    class Meta:
        unique_together = (
            ('plugin_conf', 'source')
        )

