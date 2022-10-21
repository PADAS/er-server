# Generated by Django 2.0.2 on 2018-11-02 18:53

from django.db import migrations, models
import django.db.models.deletion
import observations.models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0061_blanks'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subject',
            name='subject_subtype',
            field=models.ForeignKey(default=observations.models.get_default_subject_subtype,
                                    on_delete=django.db.models.deletion.PROTECT, to='observations.SubjectSubType'),
        ),
    ]
