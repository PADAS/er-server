#!/bin/sh
echo "running $SERVICE_NAME"
exec "$(dirname "$0")/start_${SERVICE_NAME}.sh"
