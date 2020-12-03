from django.db import migrations


def forwards(apps, schema_editor):
    SourceProvider = apps.get_model('observations', 'SourceProvider')
    db_alias = schema_editor.connection.alias

    key, display = 'and-mobile', 'And Mobile'
    SourceProvider.objects.using(db_alias).get_or_create(
        provider_key=key, display_name=display)


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0085_user_session_time'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop)
    ]
