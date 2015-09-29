import uuid
from django.db import models
from django_pgjson.fields import JsonBField
from core.models import TimestampedModel


class PluginConf(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    plugin_name = models.CharField('plugin name', max_length=100)
    configuration = JsonBField()

    def __str__(self):
        return self.plugin_name

    class Meta:
        app_label = 'data_input'


class PluginConfSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    plugin_conf = models.ForeignKey('PluginConf')
    source = models.ForeignKey('observations.Source')
    additional = JsonBField()

    class Meta:
        app_label = 'data_input'
        unique_together = (
            ('plugin_conf', 'source')
        )

