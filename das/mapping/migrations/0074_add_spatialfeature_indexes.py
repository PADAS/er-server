from django.contrib.postgres.indexes import GistIndex
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mapping", "0073_add_webmercator_geometry"),
    ]

    operations = [
        # Add optimized Web Mercator GiST index with shortened name
        migrations.AddIndex(
            model_name="spatialfeature",
            index=GistIndex(
                fields=["das_tenant_id", "feature_geometry_webmercator"],
                name="map_spatialfeat_webmerc_gist",
            ),
        ),
        # Add main geometry GiST index for spatial queries
        migrations.AddIndex(
            model_name="spatialfeature",
            index=GistIndex(
                fields=["das_tenant_id", "feature_geometry"],
                name="map_spatialfeat_geom_gist",
            ),
        ),
        # Add B-tree indexes for efficient filtering within tenant
        migrations.AddIndex(
            model_name="spatialfeature",
            index=models.Index(
                fields=["das_tenant_id", "feature_type"],
                name="map_spatialfeat_type_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="spatialfeature",
            index=models.Index(
                fields=["das_tenant_id", "spatialfile"],
                name="map_spatialfeat_file_idx",
            ),
        ),
    ]
