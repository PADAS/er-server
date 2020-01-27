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

# require "variable name" "value"
require() {
    if [ -z ${2+x} ]; then error "Required variable ${1} has not been set"; fi
}

activate_google_sdk() {
    info "Activating Google Cloud  sdk"
    gcloud auth activate-service-account secret-manager-key@earthranger-78ca55ca.iam.gserviceaccount.com --key-file=/tmp/secret_manager_key.json --project=earthranger-78ca55ca
    is_success "The Gcloud SDK has successfully been activated"
}

store_migrator_secret() {
    if [[ $(gcloud beta secrets list --format text | grep "$migrator") = *migrator* ]]; then
        # Next: Compare stored pass and new pass if != make new version of password
        info "Compare migrator role stored passoword and new password"
        (echo -n "$migrator_pass" | gcloud beta secrets versions add "$migrator" --data-file=-)
    else
        info "Create database migrator role password"
        (echo -n "$migrator_pass" | gcloud beta secrets create $migrator --data-file=- --replication-policy=automatic)
    fi
}
store_app_secret() {
    if [[ $(gcloud beta secrets list --format text | grep "$app_user") = *app* ]]; then
        # Next: Compare stored pass and new pass if != make new version of password
        info "Update database app role password"
        (echo -n "$app_user_pass" | gcloud beta secrets versions add "$app_user" --data-file=-)
    else
        info "Add database app role password"
        (echo -n "$app_user_pass" | gcloud beta secrets create "$app_user" --data-file=- --replication-policy=automatic)
    fi
}
store_analytics_secret() {
    if [[ $(gcloud beta secrets list --format text | grep "$analytics_user") = *analytics* ]]; then
        # Next: Compare stored pass and new pass if != make new version of password
        info "Update database analytics role password"
        (echo -n "$analytics_user_pass" | gcloud beta secrets versions add "$analytics_user" --data-file=-)
    else
        info "Create database analytics role password"
        (echo -n "$analytics_user_pass" | gcloud beta secrets create "$analytics_user" --data-file=- --replication-policy=automatic)
    fi
}

main() {
    activate_google_sdk
    store_migrator_secret
    store_app_secret
    store_analytics_secret
}

main
