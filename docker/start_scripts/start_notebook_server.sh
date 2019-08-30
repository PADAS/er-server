#!/bin/sh
. /startup/wait_for.sh
wait_for $DB_HOST $DB_PORT

cd /var/notebooks/

pip3 install oauth2client

python3 cfgloader.py
PYTHONPATH=/var/www/app:$PYTHONPATH
python3 /var/www/app/manage.py shell_plus --notebook --settings=das_server.notebook_settings
