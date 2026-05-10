from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analyzers", "0062_django_42"),
    ]

    operations = [
        migrations.AddField(
            model_name="movementclusteranalyzerconfig",
            name="min_subjects_in_cluster",
            field=models.IntegerField(
                default=1,
                validators=[MinValueValidator(1)],
                help_text=(
                    "Minimum number of distinct subjects required in a cluster before it is "
                    "reported as a significant event.  When greater than 1, observations from "
                    "all subjects in the subject group are combined before clustering."
                ),
                verbose_name="Minimum Subjects per Cluster",
            ),
        ),
    ]
