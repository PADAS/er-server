# Generated by Django 2.2.14 on 2021-08-20 13:52

from django.db import migrations, models
import dateutil.parser


def backfill_announcement_at(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Announcement = apps.get_model('observations', 'Announcement')

    for announcement in Announcement.objects.using(db_alias).all():
        if not announcement.announcement_at and announcement.additional:
            announcement_at = announcement.additional.get("created_at")
            if announcement_at:
                announcement_at = dateutil.parser.parse(announcement_at)
                announcement.announcement_at = announcement_at
                announcement.save()


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0107_ostrich'),
    ]

    operations = [
        migrations.AddField(
            model_name='announcement',
            name='announcement_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_announcement_at,
                             reverse_code=migrations.RunPython.noop),
    ]