#!/bin/bash

# First initialize the database to ensure all applications start up cleanly with a good DB
./docker/initDB.sh

# Runs just the api stack
./docker/reset.sh api nginx postgis redis mql worker beat rt-api
