import json
from django.db import migrations
from analyzers.subject_proximity import SUBJECT_PROXIMITY_SCHEMA

def forwards(apps, schema_editor):
    EventCategory = apps.get_model('activity', 'EventCategory')
    EventType = apps.get_model('activity', 'EventType')

    db_alias = schema_editor.connection.alias

    event_category, _ = EventCategory.objects.using(db_alias).get_or_create(value='analyzer_event',
                                                                            defaults={
                                                                                "display": "Analyzer Event",
                                                                                "ordernum": 1})
    defaults = {
        'default_priority': 200,
        'schema': json.dumps(SUBJECT_PROXIMITY_SCHEMA, indent=2, default=str),
        'display': 'Subject Proximity',
        'category_id': event_category.id

    }
    EventType.objects.using(db_alias).update_or_create(
        value='subject_proximity', defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [
        ('activity', '0106_add_accoustic_eventtype'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop)
    ]
