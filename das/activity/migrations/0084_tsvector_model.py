# Generated by Django 2.2.9 on 2020-04-07 01:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0083_alertrule_owner'),
    ]

    operations = [
        migrations.CreateModel(
            name='TSVectorModel',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
        ),
        migrations.AddField(
            model_name='tsvectormodel',
            name='event',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='activity.Event'),
        ),
    ]
