#!/bin/bash -e

###################################################################################
#
#   This script is meant to be run concourse. Pass through to our real file. 
#   Keeping this here for convention sake and to keep ci-for-ci standardized
#
###################################################################################

CI_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

$CI_DIR/environments/includes/set.das.pipeline.sh das
