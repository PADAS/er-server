from django.contrib.gis.db import models
from django.contrib.auth.models import User


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditableModel(TimestampedModel):
    user = models.ForeignKey(to=User)

    class Meta:
        abstract = True
