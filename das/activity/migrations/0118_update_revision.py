# Generated by Django 2.2.14 on 2021-04-03 21:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0117_merge_20210403_1404'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='eventattachmentrevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='eventdetailsrevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='eventfilerevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='eventnoterevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='eventphotorevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='eventrevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='patrolfilerevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='patrolnoterevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='patrolrevision',
            index_together=set(),
        ),
        migrations.AlterIndexTogether(
            name='patrolsegmentrevision',
            index_together=set(),
        ),
    ]
