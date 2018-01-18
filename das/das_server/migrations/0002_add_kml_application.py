# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.contrib.auth import get_user_model
from django.utils import six, timezone, crypto
from oauth2_provider.models import Application


def load_default_clients(apps, schema_editor):

    User = get_user_model()
    user = User.objects.get(username='das_oauth_act')

    Application(client_id='das_kml_export',
                client_type='Confidential',
                authorization_grant_type='password',
                client_secret='',
                name='DAS KML',
                skip_authorization=True,
                user=user
                ).save()


class Migration(migrations.Migration):

    dependencies = [("das_server", "0001_initial"),
                    ]

    operations = [
        migrations.RunPython(load_default_clients)
    ]
