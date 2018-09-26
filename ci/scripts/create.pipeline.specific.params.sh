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

read -p "Please enter a semantic version prefix, eg/ 'dev', 'rc', 'feature-x' (blank defaults to 'default'): " VERSION_PREFIX
echo "version-prefix: ${VERSION_PREFIX:-default}" >> $PIPELINE_PARAMS_FILE

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

read -p "Please enter the IAAS (blank defaults to gcp): " IAAS_PROVIDER
IAAS_PROVIDER=${IAAS_PROVIDER:-"gcp"}
echo "iaas: $IAAS_PROVIDER" >> $PIPELINE_PARAMS_FILE
if [ "$IAAS_PROVIDER" == "gcp" ]; then
    echo "iaas-zone: us-west1-a" >> $PIPELINE_PARAMS_FILE
    echo "iaas-workspace: padas-app" >> $PIPELINE_PARAMS_FILE
    echo "cluster-spec: deployment/cluster-specs/gcp.yaml" >> $PIPELINE_PARAMS_FILE
elif [ "$IAAS_PROVIDER" == "azure" ]; then
    echo "iaas-zone: eastus" >> $PIPELINE_PARAMS_FILE
    echo "iaas-workspace: DAS-Dev" >> $PIPELINE_PARAMS_FILE
    echo "cluster-spec: deployment/cluster-specs/azure.yaml" >> $PIPELINE_PARAMS_FILE
else
    echo "Supported IAAS are: azure, gcp but you selected $IAAS_PROVIDER"
    echo "bailing out"
    rm $PIPELINE_PARAMS_FILE
    exit 1
fi