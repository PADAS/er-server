#!/bin/bash -e
PROJECT=padas-app

CUR_REF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INFRA_DIR="$CUR_REF_DIR/../../infrastructure"
DAS_DIR="$INFRA_DIR/deployments/$PROJECT"

source $INFRA_DIR/ci/utility/ci.for.ci.utilities.sh
login_to_concourse $PROJECT $DAS_DIR

PIPELINE=${1-das}
OVERRIDES=${@:2}

fly -t $PROJECT set-pipeline -p $PIPELINE \
    -c $CUR_REF_DIR/das.pipeline.yml \
    "$(set_var_file_if_exists "$CUR_REF_DIR/$PIPELINE.params.yml")" \
    -v server-private-key="$(cat<$DAS_DIR/ci/keys/das.server)" \
    -v web-private-key="$(cat<$DAS_DIR/ci/keys/das.web)" \
    -v gcr-io-password="$(cat<$DAS_DIR/container-registry/container-registry-push.key)" \
    -v gcr-io-cluster-admin-password="$(cat<$DAS_DIR/k8s/cluster-admin.key)" \
    -v gcr-io-infrastructure-password="$(cat<$INFRA_DIR/deployments/ss-infrastructure/container-registry/container-registry-pull.key)" \
    -v gcr-io-email=1234@5678.com \
    -v gcr-io-username=_json_key \
    "$(set_var_file_if_exists "$DAS_DIR/k8s/$PIPELINE.params.yml")" \
    $OVERRIDES \  