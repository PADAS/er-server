apt-get install jq -y
gcloud container clusters describe das-dev --zone us-west1-a --format json | jq -r ".masterAuthorizedNetworksConfig.cidrBlocks[] | .cidrBlock" | sed -z 's/\n/,/g;s/,$/\n/'
