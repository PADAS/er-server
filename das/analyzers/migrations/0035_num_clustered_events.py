from django.db import migrations, models


GENERIC_GFW_TREE_LOSS_SCHEMA = """{
   "schema":{
      "$schema":"http://json-schema.org/draft-04/schema#",
      "title":"Event Type Global Forest Watch Tree Loss Alert",
      "type":"object",
      "properties":{
         "subscription_name":{
            "type":"string",
            "title":"Name of subscription with Global Forest Watch"
         },
         "alert_link":{
            "type":"string",
            "title":"URL of the map for this alert",
            "format":"uri"
         },
         "confidence":{
            "type":"number",
            "title":"Confidence level of alert"
         },
         "num_clustered_alerts":{
            "type":"number",
            "title":"Number of clustered alerts"
         }
      }
   },
   "definition":[
      "subscription_name",
      "alert_link",
      "confidence",
      "num_clustered_alerts"
   ]
}"""

GENERIC_GFW_ACTIVE_FIRE_SCHEMA = """{
   "schema":{
      "$schema":"http://json-schema.org/draft-04/schema#",
      "title":"Event Type Global Forest Watch Active Fire Alert",
      "type":"object",
      "properties":{
         "bright_ti4": {
            "type": "string",
            "title": "VIIRS I-4 channel brightness (Kelvin)"
         },
         "bright_ti5": {
            "type": "string",
            "title": "VIIRS I-5 channel brightness (Kelvin)"
         },
         "scan": {
            "type": "string",
            "title": "VIIRS Scan"
         },
         "track": {
            "type": "string",
            "title": "Satellite Track"
         },
         "frp": {
            "type": "string",
            "title": "Fire Radiative Power (MW)"
         },
         "test": {
            "type": "string",
            "title": "This is a test field on an Analyzer Event"
         },
         "subscription_name":{
            "type":"string",
            "title":"Name of subscription with Global Forest Watch"
         },
         "alert_link":{
            "type":"string",
            "title":"URL of the map for this alert",
            "format":"uri"
         },
         "confidence":{
            "type":"string",
            "title":"Confidence level of alert"
         },
         "num_clustered_alerts":{
            "type":"number",
            "title":"Number of clustered alerts"
         }
      }
   },
   "definition":[
      "bright_ti4",
      "bright_ti5",
      "scan",
      "track",
      "frp",
      "test",
      "subscription_name",
      "alert_link",
      "confidence",
      "num_clustered_alerts"
   ]
}"""


def forwards(apps, schema_editor):
    EventCategory = apps.get_model('activity', 'EventCategory')
    EventType = apps.get_model('activity', 'EventType')

    db_alias = schema_editor.connection.alias

    category, created = EventCategory.objects.using(db_alias).get_or_create(
        value='analyzer_event',
        display='Analyzer Event',
        ordernum=1)

    gfw_tree_loss_defaults = {'schema': GENERIC_GFW_TREE_LOSS_SCHEMA, 'display': 'GLAD Tree-Loss Alert (GFW)',
                'category_id': category.id, 'icon': 'deforestation_rep'}

    EventType.objects.using(db_alias).update_or_create(
        value="gfw_glad_alert",
        defaults=gfw_tree_loss_defaults
    )

    gfw_activefire_alert_defaults = {'schema': GENERIC_GFW_ACTIVE_FIRE_SCHEMA, 'display': 'Active Fire Alert (GFW)',
                'category_id': category.id, 'icon': 'fire_rep'}

    EventType.objects.using(db_alias).update_or_create(
        value="gfw_activefire_alert",
        defaults=gfw_activefire_alert_defaults
    )


class Migration(migrations.Migration):
    dependencies = [
        ('analyzers', '0034_auto_20200225_1159'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop)
    ]
