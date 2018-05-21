#!/bin/bash

# We need to start the daemon
atd
echo /startup/add-prometheus-data-source.sh $PROMETHEUS_URL | at now + 2 minutes

/run.sh

