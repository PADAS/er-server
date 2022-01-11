apt-get -qq install jq -y
gcloud config set project earthranger-78ca55ca -q --no-user-output-enabled > /dev/null
gcloud container clusters describe das-dev --zone us-west1-a --format json | jq -r ".masterAuthorizedNetworksConfig.cidrBlocks[] | .cidrBlock" | sed -z 's/\n/,/g;s/,$/\n/'
