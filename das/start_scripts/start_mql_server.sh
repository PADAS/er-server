#!/bin/bash
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

. $(dirname "$0")/django_common_startup.sh

# Run the command and filter stderr in real-time
# Only pass through lines that don't contain common Django warning patterns
uv run python3 manage.py message_queue_listeners 2> >(grep -v -E "^(RemovedInDjango|DeprecationWarning|UserWarning|RuntimeWarning)" >&2)
