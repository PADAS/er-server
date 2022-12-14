# Generated by Django 2.2.14 on 2021-12-06 14:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('activity', '0124_event_time_index'),
        ('observations', '0110_sensors'),
        ('reports', '0004_auto_20211028_1645'),
    ]

    operations = [
        migrations.CreateModel(
            name='SourceProviderEvent',
            fields=[
                ('id', models.AutoField(auto_created=True,
                 primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                 related_name='sources_provider_event', related_query_name='source_provider_event', to='activity.Event')),
                ('source_provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                 related_name='events_reached_threshold', related_query_name='event_reached_threshold', to='observations.SourceProvider')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SourceEvent',
            fields=[
                ('id', models.AutoField(auto_created=True,
                 primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                 related_name='sources_event', related_query_name='source_event', to='activity.Event')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events_reached_threshold',
                 related_query_name='event_reached_threshold', to='observations.Source')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
