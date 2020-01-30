#!/bin/bash

SERVER_BRANCH=develop
WEB_BRANCH=develop
INGRESS_BRANCH=develop

SERVER_DIGEST=$(gcloud container images list-tags gcr.io/padas-app/circleci/das-server/${SERVER_BRANCH} --filter="tags:latest" --format="value(Digest)")
INGRESS_DIGEST=$(gcloud container images list-tags gcr.io/padas-app/circleci/das-ingress/${INGRESS_BRANCH} --filter="tags:latest" --format="value(Digest)")
WEB_DIGEST=$(gcloud container images list-tags gcr.io/padas-app/circleci/das-web/${WEB_BRANCH} --filter="tags:latest" --format="value(Digest)")

SERVER_VERSION="gcr.io/padas-app/circleci/das-server/${SERVER_BRANCH}@${SERVER_DIGEST}"
WEB_VERSION="gcr.io/padas-app/circleci/das-web/${WEB_BRANCH}@${WEB_DIGEST}"
INGRESS_VERSION="gcr.io/padas-app/circleci/das-ingress/${INGRESS_BRANCH}@${INGRESS_DIGEST}"

tee MY_MANIFEST <<EOF
SERVER_VERSION="gcr.io/padas-app/circleci/das-server/${SERVER_BRANCH}@${SERVER_DIGEST}"
WEB_VERSION="gcr.io/padas-app/circleci/das-web/${WEB_BRANCH}@${WEB_DIGEST}"
INGRESS_VERSION="gcr.io/padas-app/circleci/das-ingress/${INGRESS_BRANCH}@${INGRESS_DIGEST}"
EOF


