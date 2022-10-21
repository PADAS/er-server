# Generated by Django 2.2.9 on 2021-03-30 18:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0115_patroltype_icons'),
    ]

    operations = [
        migrations.CreateModel(
            name='PatrolConfiguration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('subject_groups', models.ManyToManyField(blank=True, related_name='groups', to='observations.SubjectGroup')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]