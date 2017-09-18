#!/bin/sh

. /startup/wait_for.sh
wait_for $API_HOST $API_PORT

cd /var/notebooks/

PYTHONPATH=/var/www/app:$PYTHONPATH
python3 /var/www/app/manage.py shell_plus --notebook --settings=das_server.notebook_settings
