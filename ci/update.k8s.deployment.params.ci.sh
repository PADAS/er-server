#!/bin/bash -e


###################################
#
# This script is meant to be a bridge between concourse with known paths and variables
# And a file `update.k8s.sha.local.sh` that is generic enough to be run on our local machine
#
###################################

UPDATE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

OUTPUT_DIR=deployment-info
INPUT_DIR=git-server/deployment

GIT_SERVER_SHA=$(cat < git-server/sha)
GIT_WEB_SHA=$(cat < git-web/sha)
GIT_UTILITY_SHA=$(cat < git-utility/sha)

$UPDATE_DIR/update.k8s.deployment.params.local.sh \
    $OUTPUT_DIR \
    $INPUT_DIR \
    $GIT_SERVER_SHA \
    $GIT_WEB_SHA \
    $GIT_UTILITY_SHA
