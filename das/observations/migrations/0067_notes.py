# Generated by Django 2.0.2 on 2019-04-22 16:18

from django.db import migrations, models
import django.db.models.deletion
import observations.models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0066_attendant'),
    ]

    operations = [
        migrations.AddField(
            model_name='sourceprovider',
            name='notes',
            field=models.TextField(blank=True, null=True),
        ),
    ]