from django.contrib.gis.db import models
from django.contrib.auth.models import User


class TimestampedModel(models.Model):
    create_datetime = models.DateTimeField(auto_now_add=True)
    last_modified_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditableModel(TimestampedModel):
    user = models.ForeignKey(to=User)

    class Meta:
        abstract = True
