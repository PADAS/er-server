# Generated by Django 2.0.2 on 2019-03-23 23:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('choices', '0009_snareaction'),
    ]

    operations = [
        migrations.AlterField(
            model_name='choice',
            name='value',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]