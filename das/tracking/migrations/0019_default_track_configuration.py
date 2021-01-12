from django.db import migrations, models


def default_track_configuration(app_registry, schema_editor):
    db_alias = schema_editor.connection.alias
    config = app_registry.get_model('tracking', 'SourceProviderConfiguration')
    config.objects.using(db_alias).get_or_create()


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0018_source_provider_configuration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sourceproviderconfiguration',
            name='is_default',
            field=models.BooleanField(default=True, help_text='Used this as the default configuration',
                                      verbose_name='Use as default?'),
        ),
        migrations.RunPython(default_track_configuration, reverse_code=migrations.RunPython.noop)
    ]
