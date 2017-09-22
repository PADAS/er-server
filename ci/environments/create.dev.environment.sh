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
#  1: ENVIRONMENT_NAME=REQUIRED Which branch to pull from
############################################################################

if [ $# -eq 0 ]; then
    echo "Create a pipeline, Create a cluster, and Enable that pipeline to deploy to that cluster"
    echo "USAGE:"
    echo "  1: ENVIRONMENT_NAME=REQUIRED Name of the environment to create: This will be branchname/cluster name/pipeline name"
    echo "  Note: ENVIRONMENT_NAME will also be the name of the k8s cluster and Concourse pipeline that are created"
    echo "  Note: ENVIRONMENT_NAME will override the 'server-branch-name' setting in your custom params file, if you created one"
    echo "  Note: Google does not like _ and special characters in cluster name; lowercase letters/numbers with - is best"
    echo "  2: CLUSTER_NAME=OPTIONAL Defaults to ENVIRONMENT_NAME if not set."
    echo "This script can be run from anywhere."
    exit 1
fi

DEV_CREATE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT=padas-app
ENVIRONMENT_NAME=$1
CLUSTER_NAME=${2-$ENVIRONMENT_NAME}


##################################################################################
# Create CI Pipeline
##################################################################################
$DEV_CREATE_DIR/includes/set.dev.pipeline.happy.path.sh $ENVIRONMENT_NAME $CLUSTER_NAME
fly -t $PROJECT unpause-pipeline -p $ENVIRONMENT_NAME
