# Generated by Django 2.2.9 on 2021-03-24 11:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0096_add_subtypes_icons'),
    ]
    operations = [
        migrations.AlterField(
            model_name='source',
            name='model_name',
            field=models.CharField(
                max_length=201, null=True, verbose_name='device model name'),
        )
    ]
