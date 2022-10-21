#!/bin/sh
 
# Collect static when running with DEV=True. Otherwise assume static files
# are already in place from build.
if [ "$(echo $DEV | tr [[:upper:]] [[:lower:]])" = "true" ]; then
   echo "DEV=${DEV} so running collectstatic now"
   python3 manage.py collectstatic --no-input
fi
