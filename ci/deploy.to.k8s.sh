#!/bin/bash

echo "PROJECT_ID=$PROJECT_ID"
echo "CLUSTER_NAME=$CLUSTER_NAME"
echo "DEPLOY_PATH=$DEPLOY_PATH"

KEY_FILE=$(mktemp -u cluster-XXXXXXXXXX)
echo $CLUSTER_ADMIN_PASSWORD > $KEY_FILE

gcloud auth activate-service-account --key-file=$KEY_FILE
rm -f $KEY_FILE

gcloud config set project $PROJECT_ID
gcloud config set compute/zone us-west1-a
gcloud container clusters get-credentials $CLUSTER_NAME
kubectl config get-clusters
kubectl get all
kubectl apply -f $DEPLOY_PATH
