
#########################################
#
# Include functions for setting other pipelines. Used by other scripts.
# 
#########################################

CREATOR="$(whoami)"
__SET_PIPELINE_DIR__="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INFRA_DIR="$__SET_PIPELINE_DIR__/../../../../infrastructure"
DEPLOYMENTS_DIR="$INFRA_DIR/deployments"
PADAS_DIR="$DEPLOYMENTS_DIR/padas-app"



function set-pipeline()
{
    local PIPELINE=${1}
    local PIPELINE_TYPE=${2}
    local PIPELINE_NAME_PREFIX=${3}
    local OVERRIDES=${@:4}

    local PROJECT=padas-app

    local YAML_PATH="$__SET_PIPELINE_DIR__/../.."
    local PIPELINE_NAME="$PIPELINE_NAME_PREFIX$PIPELINE"

    source $__SET_PIPELINE_DIR__/ci.for.ci.utilities.sh

    login_to_concourse $PROJECT $PROJECT_DIR

    #SET_PIPELINE_NON_INTERACTIVE is set by concourse as an environment variable. ignore it when running locally
    fly -t $PROJECT sp -p $PIPELINE_NAME $SET_PIPELINE_NON_INTERACTIVE \
        -c $YAML_PATH/pipelines/$PIPELINE_TYPE.pipeline.yaml \
        -l $YAML_PATH/params/default.safe.params.yaml \
        "$(set_var_file_if_exists "$YAML_PATH/params/$PIPELINE.params.yaml")" \
        -v creator=$CREATOR \
        -v pipeline-name=$PIPELINE_NAME \
        -v gcr-io-email=1234@5678.com \
        -v gcr-io-username=_json_key \
        $OVERRIDES
}
