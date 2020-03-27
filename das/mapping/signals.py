from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.db import transaction
from mapping import models


@receiver(pre_save, sender=models.SpatialFile)
@receiver(pre_save, sender=models.SpatialFeatureFile)
def check_features(sender, instance, **kwargs):
    # Incase of a new spatialfile clear initially created features
    if not instance._state.adding:
        previous = sender.objects.get(id=instance.id)
        if previous.data != instance.data:
            tables = [models.SpatialFeature, models.LineFeature,
                      models.PointFeature, models.PolygonFeature]
            for table in tables:
                try:
                    table.objects.filter(spatialfile=instance).delete()
                except Exception:
                    pass
