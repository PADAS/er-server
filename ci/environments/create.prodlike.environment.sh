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
#  1: ENVIONMENT_NAME=REQUIRED What is the name of the pipeline to remove
############################################################################

if [ $# -eq 0 ]; then
    echo "Create a pipeline to deploy to your cluster"
    echo "USAGE:"
    echo "  1: ENVIONMENT_NAME=REQUIRED What is the name of the envionment to create: This will be branchname/cluster name/ pipeline name"
    echo "      Note: Google does not like _ and special characters in cluster name lowercase letters/numbers with - is best"
    echo "This script can be run from anywhere."
    exit 1
fi

DEV_CREATE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT=padas-app
ENVIONMENT_NAME=$1

##################################################################################
# Create CI Pipeline
##################################################################################

# if there is a custom set pipeline for this environment use that
PIPELINE_PARAMS="$DEV_CREATE_DIR/../params/$ENVIONMENT_NAME.params.yaml"
if [ -e $PIPELINE_PARAMS ]; then
    $DEV_CREATE_DIR/includes/set.deployment.pipeline.sh $ENVIONMENT_NAME
else
    echo "You must create a <environmentname>.params.yaml with all the right variables to be able to run this script."
    echo "$PIPELINE_PARAMS does not exist."
    exit 1
fi

#HACK, copy/pasta 'deploy-to-' one of many things to clean up in future interations.
fly -t $PROJECT unpause-pipeline -p deploy-to-$ENVIONMENT_NAME

# NOT CREATING DISKS. THE CI BUILD ALREADY DOES THAT, BETTER TO HAVE A RECORD OF THEM THERE
# BEFORE TO LONG WE CAN HAVE THE CI BUILD CREATE THE CLUSTER TO AND THEN THI ISN' NEEDED

##################################################################################
# Create Cluster
##################################################################################
$DEV_CREATE_DIR/../../../infrastructure/resources/k8s/create.gcp.cluster.sh $PROJECT $ENVIONMENT_NAME n1-highmem-4 6 false skip
