#!/bin/bash -e
CUR_REF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

PIPELINE=${1-das}
OVERRIDES=${@:2}

fly -t das set-pipeline -p $PIPELINE \
    -c $CUR_REF_DIR/das.pipeline.yaml \
    -l $CUR_REF_DIR/das.params.yaml \
    -v server-private-key="$(cat<$CUR_REF_DIR/../../../infrastructure/deployments/padas-app/ci/keys/das.server)" \
    -v web-private-key="$(cat<$CUR_REF_DIR/../../../infrastructure/deployments/padas-app/ci/keys/das.web)" \
    -v gcr-io-password="$(cat<$CUR_REF_DIR/../../../infrastructure/deployments/padas-app/container-registry/container-registry-push.key)" \
    -v gcr-io-cluster-admin-password="$(cat<$CUR_REF_DIR/../../../infrastructure/deployments/padas-app/k8s/cluster-admin.key)" \
    -v gcr-io-infrastructure-password="$(cat<$CUR_REF_DIR/../../../infrastructure/deployments/ss-infrastructure/container-registry/container-registry-pull.key)" \
    -l $CUR_REF_DIR/../../../infrastructure/deployments/padas-app/k8s/integration.params.yml \
    $OVERRIDES \  