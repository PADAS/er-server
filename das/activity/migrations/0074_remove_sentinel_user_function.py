# Generated by Django 2.0.2 on 2018-09-10 20:47

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0073_eventprovider'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='events', related_query_name='event', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='eventnote',
            name='created_by_user',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='eventphoto',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='event_photos', related_query_name='event_photo', to=settings.AUTH_USER_MODEL),
        ),
    ]
