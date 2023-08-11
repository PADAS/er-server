#!/usr/bin/env bash

declare current_branch=$1

er create-tenant-document $current_branch --subdomain $(echo $current_branch | tr "[:upper:]." "[:lower:]_") > tenant_data.json
test -f tenant_data.json && er create-tenants < tenant_data.json
