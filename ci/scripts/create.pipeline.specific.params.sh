#!/bin/bash -e

PIPELINE_NAME=$1
PIPELINE_TYPE=$2

CREATE_DEFAULT_PARAMS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PARAMS_FILE=$CREATE_DEFAULT_PARAMS_DIR/../params/$PIPELINE_NAME.params.yaml

if [ "$PIPELINE_NAME" == "das" ]; then
    echo 'das pipeline has no params yaml? Something is wrong. Bailing out.'
    exit 1
fi

# Script bails out if pipeline type is deployment
if [ "$PIPELINE_TYPE" == "deployment" ]; then
    echo 'Creating default parameters for deployment pipelines is not supported.'
    exit 1
fi

# Script creates a file with proper cluster name
touch $PARAMS_FILE
echo "cluster-name: $PIPELINE_NAME" >> $PARAMS_FILE

function prompt_for_branch()
{
    local REPO_NAME=$1
    local CONCOURSE_VARIABLE=$2

    read -p "Please enter a branch name for $REPO_NAME (blank defaults to develop): " BRANCH_NAME

    if [ "$BRANCH_NAME" != "" ]; then
        echo "$CONCOURSE_VARIABLE: $BRANCH_NAME" >> $PARAMS_FILE
    fi
}

prompt_for_branch das server-branch-name
prompt_for_branch das-web web-branch-name
prompt_for_branch das-react web-react-branch-name
