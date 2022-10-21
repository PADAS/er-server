# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.utils.text import slugify


def backfill_regions(apps, schema_editor):

    Region = apps.get_model('observations.Region')
    Subject = apps.get_model('observations.Subject')

    for s in Subject.objects.all():
        region = s.additional.get('region', None)
        country = s.additional.get('country', None)
        if region and country:
            slug = slugify(region + ' ' + country)
            if not Region.objects.all().filter(slug=slug):
                Region(region=region, country=country).save()


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0004_regions_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='region',
            name='slug',
            field=models.SlugField(max_length=100, unique=True),
        ),
        migrations.RunPython(backfill_regions)
    ]
