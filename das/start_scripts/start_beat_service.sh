#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

. $(dirname "$0")/django_common_startup.sh

celery -A das_server beat -l info -s ${CELERYBEAT_SCHEDULE_FILE:-/tmp/celerybeat-schedule}
