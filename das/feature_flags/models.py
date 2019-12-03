import uuid

from django.db import models


class FeatureFlag(models.Model):

    FLAG_CHOICES = (
        ('er_mobile_app_features', 'ER Mobile App Features'),
        )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(unique=True, max_length=100, choices=FLAG_CHOICES)
    value = models.BooleanField(default=False)
