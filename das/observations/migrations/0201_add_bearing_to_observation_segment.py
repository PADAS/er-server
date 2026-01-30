# Generated manually on 2026-01-28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0200_add_observation_segment_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='observationsegment',
            name='bearing_deg',
            field=models.FloatField(
                blank=True,
                help_text='Initial bearing in degrees [0,360) from start to end observation',
                null=True
            ),
        ),
    ]
