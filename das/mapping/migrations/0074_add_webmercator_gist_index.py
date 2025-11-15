from django.contrib.postgres.indexes import GistIndex
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("mapping", "0073_add_webmercator_geometry"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="spatialfeature",
            index=GistIndex(
                fields=["das_tenant_id", "feature_geometry_webmercator"],
                name="mapping_spatialfeature_tenant_webmercator_gist",
            ),
        ),
    ]
