from django.db import migrations


def forwards(apps, schema_editor):
    SourceProvider = apps.get_model('observations', 'SourceProvider')
    db_alias = schema_editor.connection.alias

    key, display = 'and-mobile', 'ER Track'
    SourceProvider.objects.using(db_alias).update_or_create(
            provider_key=key, defaults={'display_name': display})

class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0086_spraycraft'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop)
    ]
