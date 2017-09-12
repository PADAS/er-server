#!/bin/bash -e

###################################################################################
# This script is meant to be run by humans or concourse
# To satisfy concourse it should be run from the parent directory of das and the infrastructure repo
# It will set all the parameters as well as the credentials that previously lived in 
# credentials.yaml. That file required copy and paste of the creds and was likely to get out of date
# 
# To override specific parameters `-v <param name>=<value>` ie
# to set a specific branch `-v branch-name=the_branch`
#
###################################################################################

CI_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ $# -eq 0 ]; then
    echo "This script is intended to set a dev/build pipeline for the given branch/cluster/pipeline name"
    echo "By default this script will set the pipeine with parameters from ./ci/params/default.safe.params"
    echo "These values will set a pipeline that builds, they will not deploy to a cluster or utilize any static ip's or obcomm data"
    echo ""
    echo "There are two ways to provide parameters to this script."
    echo " a) By convention, if the file ci/params/<PIPELINE>.params.yaml exists the script will load values from there, and example of this is integration.params.yaml"
    echo " b) fly -v, -l and -y value overrides may be passed in as a additional params to this script as an arugment array."
    echo "    Best practice dictates creating a parmas.yaml file. However if you want to set manual overrides for this script"
    echo "    Please then create a new script that calls this one and saves the overrides in the repo so the values are known and recreatable"
    echo ""
    echo "USAGE:"
    echo "  1: PIPELINE=REQUIRED What is the name of the pipeline to set"
    echo "  2: ARGS=Optional Overrides for variables"
    echo ""
    echo "This script can be run from anywhere."
    exit 1
fi

PIPELINE=${1:?Pipeline Is Required}
OVERRIDES=${@:2}
PIPELINE_TYPE=das

source $CI_DIR/pipeline.base.sh

set-pipeline $PIPELINE $PIPELINE_TYPE "" $OVERRIDES
