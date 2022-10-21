# Generated by Django 2.2.14 on 2021-02-04 21:17

from django.db import migrations, models
import django.db.models.deletion

DUMMY_PATROL_ID = 'd8ce8e8f-e191-4d71-bc98-40949b5f0939'

def forward_f(apps, schema_editor):
    '''
    Find orphaned PatrolSegments and assign them to a dummy Patrol.
    '''
    Patrol = apps.get_model('activity', 'Patrol')
    PatrolSegment = apps.get_model('activity', 'PatrolSegment')

    db_alias = schema_editor.connection.alias

    dummy_patrol, created = Patrol.objects.using(db_alias).get_or_create(id=DUMMY_PATROL_ID,

                                                                         defaults={
                                                                             'title': 'Dummy Patrol',
                                                                             'objective': 'Collect orphaned Patrol Segments.'}
                                                                         )
    PatrolSegment.objects.filter(patrol__isnull=True).update(patrol=dummy_patrol)



class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0111_entry_alert_eventtype'),
    ]

    operations = [
        migrations.RunPython(forward_f, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='patrolsegment',
            name='patrol',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='patrol_segments',
                                    related_query_name='patrol_segment', to='activity.Patrol'),
        ),
    ]