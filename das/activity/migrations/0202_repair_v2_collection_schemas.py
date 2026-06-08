"""Neutralized: the original V2 collection-schema repair shipped here was
broken (it constructed historical ``EventTypeRevision`` rows, which raise
under django-multitenant, so it repaired nothing — see ERA-13384). Because
this migration was already marked applied in every environment, it cannot be
re-run; it is emptied to a no-op and the corrected repair is re-delivered as
``0203_repair_v2_collection_schemas`` (ERA-13385).
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0201_community_input"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
