#!/bin/bash
# This script installs the form builder pod in the given namespace, after we created a new single tenant site.
# most likely after we un-archived a site.
#
# example usage: ./install_form_builder_pod.sh 1.0.7 mpilo release-2.119.1-8da050b
# make sure gcloud is authenticated to the das-prod1 cluster

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <version> <tenant_name> <image_tag>"
    exit 1
fi

VERSION="$1"
TENANT_NAME="$2"
IMAGE_TAG="$3"

helm pull oci://europe-west3-docker.pkg.dev/padas-app/er-mt-helm/report-form-builder --version "$VERSION"

helm upgrade --install report-form-builder ./report-form-builder-"$VERSION".tgz \
    --namespace "$TENANT_NAME" \
    --timeout 10m \
    --values ../templated-deployment/templates/form-builder.yaml \
    --set image.tag="$IMAGE_TAG" \
    --wait
