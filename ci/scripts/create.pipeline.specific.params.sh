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

touch "$PIPELINE_PARAMS_FILE"
echo "cluster-name: $PIPELINE_NAME" >> "$PIPELINE_PARAMS_FILE"

while [[ -z "$VERSION_PREFIX" ]]; do
    read -r -p "Please enter a UNIQUE semantic version prefix (eg/ 'feature-x', 'bugfix-y', or your code branch name): " VERSION_PREFIX
done
echo "version-prefix: ${VERSION_PREFIX:-default}" >> "$PIPELINE_PARAMS_FILE"

function set_initial_version_from_develop()
{
    local COMPONENT_NAME=$1
    local CONCOURSE_VARIABLE=$2
    local URL="https://raw.githubusercontent.com/PADAS/das.versions/master/dev.${COMPONENT_NAME}.version"

    local TEMP_DIR
    TEMP_DIR=$(mktemp --directory)

    wget --quiet --directory-prefix "$TEMP_DIR" "$URL"

    local DEV_VERSION
    DEV_VERSION=$(cat "$TEMP_DIR/dev.${COMPONENT_NAME}.version")

    echo "$CONCOURSE_VARIABLE: ${DEV_VERSION:-0.0.0}" >> "$PIPELINE_PARAMS_FILE"

    rm -r "$TEMP_DIR"
}

set_initial_version_from_develop server initial-server-version
set_initial_version_from_develop web initial-web-version
set_initial_version_from_develop smartconnect initial-smartconnect-version

function prompt_for_branch()
{
    local REPO_NAME=$1
    local CONCOURSE_VARIABLE=$2

    read -r -p "Please enter a branch name for $REPO_NAME (blank defaults to develop): " BRANCH_NAME

    if [ "$BRANCH_NAME" != "" ]; then
        echo "$CONCOURSE_VARIABLE: $BRANCH_NAME" >> "$PIPELINE_PARAMS_FILE"
    fi
}

prompt_for_branch das server-branch-name
prompt_for_branch das-web web-branch-name
prompt_for_branch das-smartconnect-provider smartconnect-provider-branch-name

function write_nondefault_namespace_to_params_file {
    read -r -p "Please enter the namespace to which this pipeline shall deploy its components (blank defaults to 'default') : " NAMESPACE
    if [ "$NAMESPACE" != "" ]; then
        echo "namespace: $NAMESPACE" >> "$PIPELINE_PARAMS_FILE"
    fi
}

write_nondefault_namespace_to_params_file

read -r -p "Please enter the IAAS (blank defaults to gcp): " IAAS_PROVIDER

IAAS_PROVIDER=${IAAS_PROVIDER:-"gcp"}
echo "iaas: $IAAS_PROVIDER" >> "$PIPELINE_PARAMS_FILE"
if [ "$IAAS_PROVIDER" == "gcp" ]; then
    echo "iaas-zone: us-west1-a" >> "$PIPELINE_PARAMS_FILE"
    echo "iaas-workspace: padas-app" >> "$PIPELINE_PARAMS_FILE"
    echo "cluster-spec: deployment/cluster-specs/gcp.yaml" >> "$PIPELINE_PARAMS_FILE"
elif [ "$IAAS_PROVIDER" == "azure" ]; then
    echo "iaas-zone: eastus" >> "$PIPELINE_PARAMS_FILE"
    echo "iaas-workspace: DAS-Dev" >> "$PIPELINE_PARAMS_FILE"
    echo "cluster-spec: deployment/cluster-specs/azure.yaml" >> "$PIPELINE_PARAMS_FILE"
else
    echo "Supported IAAS are: azure, gcp but you selected $IAAS_PROVIDER"
    echo "bailing out"
    rm "$PIPELINE_PARAMS_FILE"
    exit 1
fi

