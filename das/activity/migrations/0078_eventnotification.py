# Generated by Django 2.0.10 on 2019-05-21 03:21

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activity', '0077_alertmodels'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventNotification',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('method', models.CharField(choices=[('email', 'Email'), ('sms', 'SMS')], default='email', max_length=20)),
                ('value', models.CharField(default='', help_text='A phone number or email address.', max_length=100)),
                ('event', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='activity.Event')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='event_notifications', related_query_name='event_notification', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
