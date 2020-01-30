#!/usr/bin/env bash
BOLD='\e[1m'
BLUE='\e[34m'
RED='\e[31m'
YELLOW='\e[33m'
GREEN='\e[92m'
NC='\e[0m'

info() {
    printf "\n${BOLD}${BLUE}====> $(echo $@) ${NC}\n"
}

warning() {
    printf "\n${BOLD}${YELLOW}====> $(echo $@)  ${NC}\n"
}

error() {

    printf "\n${BOLD}${RED}====> $(echo $@)  ${NC}\n"
    exit 1
}

success() {
    printf "\n${BOLD}${GREEN}====> $(echo $@) ${NC}\n"
}

is_success_or_fail() {
    if [ "$?" == "0" ]; then success $@; else error $@; fi
}

is_success() {
    if [ "$?" == "0" ]; then success $@; fi
}

installGoogleCloudSdk() {
    info "Installing google cloud sdk"
    echo "deb http://packages.cloud.google.com/apt cloud-sdk-jessie main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
    sudo apt-get update && sudo apt-get install google-cloud-sdk
    is_success "Gcloud has been installed successfully"
}

authWithServiceAccount() {
    require 'GCLOUD_SERVICE_KEY' $GCLOUD_SERVICE_KEY
    echo $GCLOUD_SERVICE_KEY | base64 --decode > secrets_service_key.json
    gcloud auth activate-service-account --key-file secrets_service_key.json
    is_success "Service account activated successfuly"
}

store_migrator_secret() {
    if [[ $(gcloud --quiet beta secrets list --format text | grep "$MIGRATOR") = *migrator* ]]; then
        # Next: Compare stored pass and new pass if != make new version of password
        info "Compare migrator role stored passoword and new password"
        (echo -n "$MIGRATOR_PASS" | gcloudm--quiet beta secrets versions add "$MIGRATOR" --data-file=-)
    else
        info "Create database migrator role password"
        (echo -n "$MIGRATOR_PASS" | gcloud --quiet beta secrets create $MIGRATOR --data-file=- --replication-policy=automatic)
    fi
}
# store_app_secret() {
#     if [[ $(gcloud beta secrets list --format text | grep "$app_user") = *app* ]]; then
#         # Next: Compare stored pass and new pass if != make new version of password
#         info "Update database app role password"
#         (echo -n "$app_user_pass" | gcloud beta secrets versions add "$app_user" --data-file=-)
#     else
#         info "Add database app role password"
#         (echo -n "$app_user_pass" | gcloud beta secrets create "$app_user" --data-file=- --replication-policy=automatic)
#     fi
# }
# store_analytics_secret() {
#     if [[ $(gcloud beta secrets list --format text | grep "$analytics_user") = *analytics* ]]; then
#         # Next: Compare stored pass and new pass if != make new version of password
#         info "Update database analytics role password"
#         (echo -n "$analytics_user_pass" | gcloud beta secrets versions add "$analytics_user" --data-file=-)
#     else
#         info "Create database analytics role password"
#         (echo -n "$analytics_user_pass" | gcloud beta secrets create "$analytics_user" --data-file=- --replication-policy=automatic)
#     fi
# }

main() {
    installGoogleCloudSdk
    authWithServiceAccount
    # activate_google_sdk
    store_migrator_secret
    # store_app_secret
    # store_analytics_secret
}

main
