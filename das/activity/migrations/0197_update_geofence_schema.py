import logging

from django.apps import apps
from django.db import migrations

from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.managers import TenantContextManager, UnsetDASTenantContextManager

logger = logging.getLogger(__name__)

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

    with UnsetDASTenantContextManager():
        das_tenants = DASTenant.objects.all()

    for tenant in das_tenants:
        try:
            with TenantContextManager(domain=tenant.domain):
                try:
                    EventType.objects.filter(value="geofence_break").update(schema=GEOFENCE_SCHEMA)
                except EventType.DoesNotExist:
                    logger.warning("EventType with value 'geofence_break' does not exist for tenant %s", tenant.domain)
                try:
                    EventType.objects.filter(value="proximity").update(schema=PROXIMITY_SCHEMA)
                except EventType.DoesNotExist:
                    logger.warning("EventType with value 'proximity' does not exist for tenant %s", tenant.domain)

        except (TenantNotFoundException, DASTenant.DoesNotExist):
            logger.warning(
                "Tenant with domain %s found in current cluster domain list does not exist in TMS", tenant.domain
            )


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0196_alertrule_override_message"),
    ]

    operations = [migrations.RunPython(update_geofence_event_types, migrations.RunPython.noop)]
