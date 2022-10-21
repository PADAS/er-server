# Generated by Django 2.0.2 on 2018-11-02 18:53

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.query_utils
import observations.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0062_awt'),
        ('tracking', '0010_vectronics'),
    ]

    operations = [
        migrations.CreateModel(
            name='AwtPlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, null=True, unique=True,
                                          verbose_name='Unique name to identify the plugin.')),
                ('status', models.CharField(choices=[
                 ('enabled', 'Enabled'), ('disabled', 'Disabled')], default='enabled', max_length=15)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('username', models.CharField(
                    help_text='Username for AWT service.', max_length=100)),
                ('password', models.CharField(
                    help_text='Password for AWT service.', max_length=100)),
                ('host', models.CharField(
                    help_text='API Host for AWT service.', max_length=100)),
                ('subscription_token', models.CharField(
                    help_text='Subscription Token ', max_length=200)),
                ('provider', models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                               on_delete=django.db.models.deletion.PROTECT, related_name='+', to='observations.SourceProvider')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='sourceplugin',
            name='plugin_type',
            field=models.ForeignKey(limit_choices_to=django.db.models.query_utils.Q(django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'savannahplugin'), _connector='AND'), django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'inreachplugin'), _connector='AND'), django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'demosourceplugin'), _connector='AND'), django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'awthttpplugin'), _connector='AND'), django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'inreachkmlplugin'), _connector='AND'), django.db.models.query_utils.Q(
                ('app_label', 'tracking'), ('model', 'skygisticssatelliteplugin'), _connector='AND'), django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'spidertracksplugin'), _connector='AND'), django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'awetelemetryplugin'), _connector='AND'), django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'vectronicsplugin'), _connector='AND'), django.db.models.query_utils.Q(('app_label', 'tracking'), ('model', 'awtplugin'), _connector='AND'), _connector='OR'), on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType'),
        ),
    ]
