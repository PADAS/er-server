# Generated by Django 2.0.13 on 2020-02-12 10:36

from django.db import migrations
from django.core import management


def update_eula(apps, schema_editor):
    management.call_command("update_eula",
                            version_string="EarthRanger_EULA_ver2020-02-27",
                            eula="https://earthranger.com/EULA")


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0019_rename_useragreement_accepted_field'),
    ]

    operations = [
        migrations.RunPython(update_eula)
    ]