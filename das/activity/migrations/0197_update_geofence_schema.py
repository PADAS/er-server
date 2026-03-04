# Empty migration to replace a migration that updated some analyzer event type schemas, but was causing problems.
# Decided instead to have new event types include the updates but not change existing ones.  Leaving this empty
# migration here for compatability with any Django databases that already applied this update.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0196_alertrule_override_message"),
    ]

    operations = [migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop)]
