#!/bin/bash -e

############################################################################
# 
# This is to be run by humans
# This will remove a pipeline from concourse. If you run this on the wrong pipeline, 
#   we can always recreate the pipeline, it is afterall stored in git, we can't however
#   recreat the build history so proceed carefully
#
# ARGS:
#  1: PIPELINE=REQUIRED What is the name of the pipeline to remove
############################################################################

if [ $# -eq 0 ]; then
    echo "Remove a pipeline from the server"
    echo "USAGE:"
    echo "  1: PIPELINE=REQUIRED What is the name of the pipeline to remove"
    echo "This script can be run from anywhere."
    exit 1
fi
REMOVE_PIPELINE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

PIPELINE=${1-integration}

PROJECT=padas-app

INFRA_DIR="$REMOVE_PIPELINE_DIR/../../../../infrastructure"
DEPLOYMENTS_DIR="$INFRA_DIR/deployments"
PROJECT_DIR="$DEPLOYMENTS_DIR/$PROJECT"

source $INFRA_DIR/ci/utility/ci.for.ci.utilities.sh

login_to_concourse $PROJECT $PROJECT_DIR

fly -t $PROJECT dp -p $PIPELINE
