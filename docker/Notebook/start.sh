#!/bin/sh

cd /var/notebooks/

PYTHONPATH=/var/www/app:$PYTHONPATH
python3 /var/www/app/manage.py shell_plus --notebook --settings=das_server.notebook_settings
