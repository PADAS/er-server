from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models

from observations.models import Subject


class SubjectAnalyzer(models.Model):
    """Maps Analyzer parameters to Subjects to override defaults
    """
    limits = models.Q(app_label='analyzers', model='geofenceanalyzer') \
        | models.Q(app_label='analyzers', model='immobilityanalyzer') \
        | models.Q(app_label='analyzers', model='proximityanalyzer') \
        | models.Q(app_label='analyzers', model='observationannotator')

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=limits)
    object_id = models.PositiveIntegerField()

    content_object = GenericForeignKey('content_type', 'object_id')
    subject = models.ForeignKey(to=Subject)

    @property
    def analyzer(self):
        return self.content_object

