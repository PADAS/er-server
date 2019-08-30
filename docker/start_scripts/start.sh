#!/bin/sh
echo "running $SERVICE_NAME"
exec "start_scripts/start_${SERVICE_NAME}.sh"
