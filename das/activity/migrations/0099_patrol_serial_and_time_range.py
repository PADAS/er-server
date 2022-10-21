from django.db import migrations, models, connection


def serial_next_increment():
    with connection.cursor() as cursor:
        cursor.execute("SELECT MAX(serial_number) FROM activity_patrol")
        result = cursor.fetchone()
        return (result[0] or 0) + 1


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0098_add_leader_patrolsegment'),
    ]

    operations = [
        migrations.RunSQL(
            "CREATE SEQUENCE activity_patrol_unique_serial START 1 INCREMENT 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1",
            reverse_sql="DROP SEQUENCE IF EXISTS activity_patrol_unique_serial",
            elidable=False,
        ),
        migrations.RemoveField(
            model_name='patrol',
            name='time_range',
        ),
        migrations.AlterField(
            model_name='patrol',
            name='serial_number',
            field=models.BigIntegerField(blank=True, default=serial_next_increment, null=True,
                                         unique=True, verbose_name='Serial Number'),
        ),
    ]
