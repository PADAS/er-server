import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from mapping import models
from mapping.tasks import load_spatial_features_from_files

logger = logging.getLogger(__name__)


@receiver(post_save, sender=models.SpatialFile)
@receiver(post_save, sender=models.SpatialFeatureFile)
def check_updated_feature_attributes(sender, instance, created, **kwargs):
    if not created:
        data = {instance.data: instance.prev_data,
                instance.feature_type: instance.prev_type}
        if instance.prev_set:
            data[instance.feature_set] = instance.prev_set

        for k, v in data.items():
            if k != v:
                if k == instance.data:
                    check_data_file_update(k, instance)
                created = True

    if created:
        transaction.on_commit(
            lambda: load_spatial_features_from_files(str(instance.id)))


def check_data_file_update(k, instance):
    # Incase of a new spatialfile clear initially created features
    tables = [models.SpatialFeature, models.LineFeature,
              models.PointFeature, models.PolygonFeature]
    for table in tables:
        try:
            table.objects.filter(spatialfile=instance).delete()
        except Exception:
            pass
