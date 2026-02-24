from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("observations", "0201_add_bearing_to_observation_segment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="observationsegment",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
    ]
