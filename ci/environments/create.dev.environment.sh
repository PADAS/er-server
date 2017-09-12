#!/bin/bash -e

############################################################################
# 
# This is to be run by humans
# This attempts to create an end to end environment with:
# - a ci pipeline
# - a k8s cluster
# - disks with a standard known name
# - All these things wired together
#
#   We know this is not the solution we want to have this and the infra repo dependent on each other
#   And to have limited access and several other reasons we haven't done this
#   Much like the delete cluster script, its a matter of pragmatism. We have to do this anyway
#   The more automated, the safer.
#
# ARGS:
#  1: SERVER_BRANCH_NAME=REQUIRED Which branch to pull from
############################################################################

if [ $# -eq 0 ]; then
    echo "Create a pipeline, Create a cluster, and Enable that pipeline to deploy to that cluster"
    echo "USAGE:"
    echo "  1: SERVER_BRANCH_NAME=REQUIRED Which branch to pull from"
    echo "  Note: SERVER_BRANCH_NAME will also be the name of the k8s cluster and Concoures pipeline that are created"
    echo "  Note: SERVER_BRANCH_NAME will override the 'server-branch-name' setting in your custom params file, if you created one"
    echo "  Note: Google does not like _ and special characters in cluster name; lowercase letters/numbers with - is best"
    echo "This script can be run from anywhere."
    exit 1
fi

DEV_CREATE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT=padas-app
SERVER_BRANCH_NAME=$1

##################################################################################
# Create CI Pipeline
##################################################################################
$DEV_CREATE_DIR/includes/set.dev.pipeline.happy.path.sh $SERVER_BRANCH_NAME
fly -t $PROJECT unpause-pipeline -p $SERVER_BRANCH_NAME
