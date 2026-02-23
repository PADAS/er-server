from django.apps import apps
from django.db import migrations

from utils.tenant.managers import TenantContextManager

GEOFENCE_SCHEMA = """
{
    "schema": {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "EventType Geofencing",
        "type": "object",
        "readonly": true,
        "properties": {
            "name": {
                "title": "Name of subject",
                "type": "string"
            },
            "total_fix_count": {
                "title": "Total Fix Count",
                "type": "number"
            },
            "subject_heading": {
                "title": "Subject Heading",
                "type": "number"
            },
            "contain_regions": {
                "title": "Current Region",
                "type": "string"
            },
            "details": {
                "title": "Details",
                "type": "string"
            },
            "subject_speed_kmhr": {
                "title": "Subject Speed",
                "type": "number"
            },
            "geofence_name": {
                "title": "Geofence Name",
                "type": "string"
            },
            "feature_group_name": {
                "title": "Geofence Feature Group",
                "type": "string"
            }
        },
        "definition": [
            "name",
            "details",
            "geofence_name",
            "feature_group_name",
            "contain_regions",
            "subject_speed_kmhr",
            "subject_heading",
            "total_fix_count"
        ]
    }
}
    """

PROXIMITY_SCHEMA = """
{
    "schema": {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "EventType Proximity",
        "type": "object",
        "definition": [
            "name",
            "details",
            "spatial_feature_name",
            "spatial_feature_group",
            "subject_speed_kmhr",
            "subject_heading",
            "total_fix_count",
            "proximity_dist_meters"
        ],
        "properties": {
            "name": {
                "title": "Name of subject",
                "type": "string"
            },
            "details": {
                "title": "Details",
                "type": "string"
            },
            "spatial_feature_name": {
                "title": "Spatial Feature Name",
                "type": "string"
            },
            "spatial_feature_group": {
                "title": "Spatial Feature Group",
                "type": "string"
            },
            "subject_speed_kmhr": {
                "title": "Subject Speed",
                "type": "number"
            },
            "subject_heading": {
                "title": "Subject Heading",
                "type": "number"
            },
            "total_fix_count": {
                "title": "Total Fix Count",
                "type": "number"
            },
            "proximity_dist_meters": {
                "title": "Proximity Distance Meters",
                "type": "number"
            }
        }
    }
}
"""


def update_geofence_event_types(_migration_apps, _):

    EventType = apps.get_model("activity", "EventType")
    DASTenant = apps.get_model("core", "DASTenant")

    for tenant in DASTenant.objects.all():
        with TenantContextManager(domain=tenant.domain):
            EventType.objects.filter(
                das_tenant_id=tenant.id, id="57943092-b817-43cc-a67c-c7704e59f6ea", value="geofence_break"
            ).update(schema=GEOFENCE_SCHEMA)

            EventType.objects.filter(
                das_tenant_id=tenant.id, id="c96620be-9d3d-416c-86e6-c0daa64a7063", value="proximity"
            ).update(schema=PROXIMITY_SCHEMA)


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0196_alertrule_override_message"),
    ]

    operations = [migrations.RunPython(update_geofence_event_types, migrations.RunPython.noop)]
