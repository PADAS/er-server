#!/bin/bash -e

############################################################################
# 
# This is to be run by humans or other scripts.
# As Dev's we often want to spin up an entire stack, from ci pipeline to cluster 
# We also want this to happen automagically.
# 
# In this new world there are lots and lots of moving parts.
# The main moving part is a pipeline on the integration server call 'integration'
# This pipeline is set with all the correct variables to:
#   Deploy develop to a k8s cluster named 'integration'
#
# That pipeline is created with a script that lives next to this that is called 'set.pipeline.sh' 
# That pipeline takes many inputs. These inputs tend to be in 1 of two groups:
#   Credentials stored outside of this repo
#   Specific variables to pass to concourse. Those variables are stored in the 'params/*.params.yaml'
#
# When the set.pipeline script talks to concourse it uses the concourse command line program, called 'fly'
# Fly allows us to override the aforementioned variables at our leisure.
#
# This script attempts to set the most possibly destructive variables in a way that ensure we don't accidentally
# do any harm. It is created for a 'happy path'. 
# Specifically, this will work for you as-is, provided:
#   1) You have changes only to vic_server
#   2) You don't want to run a collector (this should be change to a more useful default when we have 'realtime' again)
#   3) You have created or will create a k8s cluster `./infrastructure/resources/k8s/create.gcp.cluster.sh`
#
# At a minimum, for a given set of branches that you want deployed to a cluster, you can copy this file, hard code the branch name
# As well as any other variables and then you don't have to remember each time you need to make a pipeline change, what you set to what
# You will i'm sure get reminded to delete it at PR time :)
#
# ARGS:
#  1: BRANCH_NAME=REQUIRED What is the name of your branch (this will also be your pipeline name as well as your cluster name if cluster name is not also provided)
#  2: CLUSTER_NAME=OPTIONAL Name of cluster. If omitted, will take the value of BRANCH_NAME
############################################################################

if [ $# -eq 0 ]; then
    echo "Create a pipeline to deploy to your cluster"
    echo "USAGE:"
    echo "  1: BRANCH_NAME=REQUIRED This is the name of the branch you are building. We will also set it as the pipeline name, as well as cluster name if cluster name is not provided."
    echo "  2: CLUSTER_NAME=OPTIONAL This is the name of the cluster. If omitted, BRANCH_NAME will be used for the cluster name."
    echo "This script can be run from anywhere."
    exit 1
fi
SET_PIPELINE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

BRANCH_NAME=$1
CLUSTER_NAME=${2-$BRANCH_NAME}

$SET_PIPELINE_DIR/set.das.pipeline.sh $BRANCH_NAME \
    -v server-branch-name=$BRANCH_NAME \
    -v cluster-name=$CLUSTER_NAME \
    -v disk-namespace=$CLUSTER_NAME \
    -v version-suffix="$BRANCH_NAME"
