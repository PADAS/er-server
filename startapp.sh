#!/bin/bash

cd /var/www/das
export DJANGO_SETTINGS_MODULE=das_server.local_settings
python3 manage.py migrate
python3 manage.py runserver 0.0.0.0:8000