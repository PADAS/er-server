#!/bin/bash -e

############################################################################
# 
# This is to be run by humans
# This attempts to destroy an end to end environment with:
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
#  1: ENVIRONMENT_NAME=REQUIRED What is the name of the pipeline to remove
############################################################################

if [ $# -eq 0 ]; then
    echo "Delete a dev pipeline, cluster, and disks"
    echo "USAGE:"
    echo "  1: ENVIRONMENT_NAME=REQUIRED What is the name of the environment to destroy: This will be branch name/cluster name/pipeline name"
    echo "This script can be run from anywhere."
    exit 1
fi

DEV_CREATE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT=padas-app
ENVIRONMENT_NAME=$1

##################################################################################
# Delete CI Pipeline
##################################################################################
fly -t $PROJECT dp -p $ENVIRONMENT_NAME

##################################################################################
# Delete Cluster
##################################################################################
INFRA_DIR_X="$DEV_CREATE_DIR/../../../infrastructure"
$INFRA_DIR_X/resources/k8s/delete.gcp.cluster.sh $PROJECT $ENVIRONMENT_NAME

##################################################################################
# Delete Disks
##################################################################################
DEFAULT_DISKS_LOCATION="$DEV_CREATE_DIR/../../deployment/storage/default.disks.csv"
$INFRA_DIR_X/resources/cloud/gcp/disks/delete.from.csv.sh $PROJECT $ENVIRONMENT_NAME $DEFAULT_DISKS_LOCATION
