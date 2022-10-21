# Generated by Django 2.2.9 on 2020-11-20 16:03

from django.db import migrations, models

UPDATE_NAME_SPF = """
with t0 as (select id, name, row_number() over (partition by name order by created_at) seq
from mapping_spatialfeaturetype)
update mapping_spatialfeaturetype sft
set name = sft.name || '-' || t0.seq
from t0
where t0.id = sft.id
and t0.seq > 1;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0034_update_arcgis_url'),
    ]

    operations = [
        migrations.RunSQL(UPDATE_NAME_SPF, reverse_sql=migrations.RunSQL.noop),
        migrations.AlterField(
            model_name='spatialfeaturetype',
            name='name',
            field=models.CharField(max_length=255, unique=True),
        ),
    ]
