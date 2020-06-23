#!/bin/bash

# Collect static when running with DEV=True. Otherwise assume static files
# are already in place from build.
if [[ "${DEV,,}" == "true" ]]; then
  python3 manage.py collectstatic --no-input
fi
