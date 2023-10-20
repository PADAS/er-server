#!/usr/bin/env bash

declare current_branch=$1
declare cluster_namespace=$2
declare cluster_name=$3

er create-tenant-document $current_branch --cluster-namespace $cluster_namespace --cluster-name $cluster_name \
    --subdomain $(echo $current_branch | tr "[:upper:]." "[:lower:]_") > tenant_data.json

test -f tenant_data.json && er create-tenants < tenant_data.json
