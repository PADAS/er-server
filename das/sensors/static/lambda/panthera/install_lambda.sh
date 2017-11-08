#!/bin/bash -e

PROJECT_DIR=$PWD
ROLE_ARN='das_server-dev'
PROFILE='PANTHERA'

aws lambda create-function \
--region us-west-2 \
--function-name PostPantheraCameraTrapImage \
--zip-file fileb:/$PROJECT_DIR/panthera-camera-trap.zip \
--role $ROLE_ARN \
--handler panthera-camera-trap.handler \
--runtime python3.6 \
--profile $PROFILE \
--timeout 60 \
--memory-size 1024