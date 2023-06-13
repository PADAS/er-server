from django.db import migrations


def create_bicycle_patrol_type(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    PatrolType = apps.get_model("activity", "PatrolType")

    bike_patrol, _ = PatrolType.objects.using(db_alias).get_or_create(value="bicycle_patrol")
    bike_patrol.is_active = True
    bike_patrol.icon = "bicycle-patrol-icon"
    bike_patrol.display = "Bicycle Patrol"
    bike_patrol.ordernum = 40
    bike_patrol.save()


class Migration(migrations.Migration):
    dependencies = [("activity", "0138_catlen")]
    operations = [migrations.RunPython(code=create_bicycle_patrol_type, reverse_code=migrations.RunPython.noop)]
