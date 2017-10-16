#!/bin/bash -e

###################################################################################
# Run by set pipeline automation in the tools container
# Creates a pipeline specific params file with some intelligent defaults.
# This is provided merely for convenience.
###################################################################################

PIPELINE_NAME=$1
PIPELINE_TYPE=$2
PIPELINE_PARAMS_FILE=$3

if [ "$PIPELINE_NAME" == "integration" ]; then
    echo 'integration pipeline has no params yaml? Something is wrong. Bailing out.'
    exit 1
fi

# Be very intentional with deployment pipelines -- we will not auto-create them.
if [ "$PIPELINE_TYPE" == "deployment" ]; then
    echo 'Creating pipeline-specific parameters for deployment pipelines is not supported.'
    exit 1
fi

touch $PIPELINE_PARAMS_FILE
echo "cluster-name: $PIPELINE_NAME" >> $PIPELINE_PARAMS_FILE

function prompt_for_branch()
{
    local REPO_NAME=$1
    local CONCOURSE_VARIABLE=$2

    read -p "Please enter a branch name for $REPO_NAME (blank defaults to develop): " BRANCH_NAME

    if [ "$BRANCH_NAME" != "" ]; then
        echo "$CONCOURSE_VARIABLE: $BRANCH_NAME" >> $PIPELINE_PARAMS_FILE
    fi
}

prompt_for_branch das server-branch-name
prompt_for_branch das-web web-branch-name
prompt_for_branch das-react web-react-branch-name
