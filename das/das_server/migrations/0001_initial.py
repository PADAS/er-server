# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.contrib.auth import get_user_model
from django.utils import six, timezone, crypto
from oauth2_provider.models import Application

def load_default_clients(apps, schema_editor):

    User = get_user_model()

    if not User.objects.filter(username='das_oauth_act').exists():
        user = User(username='das_oauth_act',
             email='das_oauth_act@das.org',
             first_name='das',
             last_name='oauth',
             password=crypto.get_random_string(),
             is_active=False,
             last_login=timezone.now())
        user.save()

        #Application = apps.get_model('oauth2_provider.Application')

        Application(client_id='das_web_client',
                    client_type='Confidential',
                    authorization_grant_type='password',
                    client_secret='',
                    name='DAS Web',
                    skip_authorization=True,
                    user=user
                    ).save()
        Application(client_id='das_ios_client',
                    client_type='Confidential',
                    authorization_grant_type='password',
                    client_secret='',
                    name='DAS IOS App',
                    skip_authorization=True,
                    user=user
                    ).save()

class Migration(migrations.Migration):

    dependencies = [("oauth2_provider", "0005_auto_20170514_1141"),
    ]

    operations = [
        migrations.RunPython(load_default_clients)
    ]
