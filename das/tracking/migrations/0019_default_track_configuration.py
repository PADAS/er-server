from django.db import migrations, models


def default_track_configuration(app_registry, schema_editor):
    db_alias = schema_editor.connection.alias
    subjectgroup = app_registry.get_model('tracking', 'SourceProviderConfiguration')
    subjectgroup.objects.using(db_alias).get_or_create(is_default=True)


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0018_source_provider_configuration'),
    ]

    operations = [
        migrations.RunPython(default_track_configuration, reverse_code=migrations.RunPython.noop)
    ]
