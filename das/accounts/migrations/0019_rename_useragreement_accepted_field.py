# Generated by Django 2.2.9 on 2020-02-18 14:19

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_EarthRanger_EULA_ver2020-02-12'),
    ]

    operations = [
        migrations.RenameField(
            model_name='useragreement',
            old_name='accepted',
            new_name='accept',
        ),
    ]
