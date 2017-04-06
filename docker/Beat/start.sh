#!/bin/sh
cd /var/www/das
. ./wait_for.sh

wait_for

celery -A das_server beat -l info -s /tmp/celerybeat-schedule