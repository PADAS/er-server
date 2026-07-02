"""Neutralized: this data migration ran the V2 collection-schema repair
automatically on every deploy across all tenants (ERA-13385). Because it has
already been applied in every environment it cannot be deleted (that would
break migration-state consistency), so it is emptied to a no-op.

The repair logic now lives in the management command
``repair_v2_collection_schemas`` (``activity/management/commands/
repair_v2_collection_schemas.py``), which must be run explicitly and is
scoped to a single tenant via ``--tenant_domain``.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0202_repair_v2_collection_schemas"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
