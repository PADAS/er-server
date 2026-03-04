from django.db import migrations

logger = logging.getLogger(__name__)


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0196_alertrule_override_message"),
    ]

    operations = [migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop)]
