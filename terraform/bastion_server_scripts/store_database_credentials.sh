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
    gcloud auth activate-service-account secret-manager-api-access@bench-projects.iam.gserviceaccount.com --key-file=/tmp/test-service-account.json --project=bench-projects
    is_success "The Gcloud SDK has successfully been activated"
}

store_migrator_secret() {
    info "Add database migrator secret"

}
main() {
    activate_google_sdk
}

main
