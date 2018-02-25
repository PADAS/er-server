#!/bin/bash -e

###################################
#
# Run this script with the required paramaters on your local machine to update all the
# k8s Deployment files where in they have any environment variables with in them
# replaced with the ones exported below.
# Concourse calls this script via the 'update.k8s.sha.ci.sh' with all the required parameters
#
###################################

OUTPUT_DIR=${1:?Output Dir Required}
INPUT_DIR=${2:?Input Dir Required}
export GIT_SERVER_SHA=${3:?Server SHA Required}
export GIT_WEB_SHA=${4:?WEB SHA Required}
export GIT_UTILITY_SHA=${6:?Utility SHA Required}

echo "OUTPUT_DIR=$OUTPUT_DIR"
echo "INPUT_DIR=$INPUT_DIR"
echo "GIT_SERVER_SHA=$GIT_SERVER_SHA"
echo "GIT_WEB_SHA=$GIT_WEB_SHA"
echo "GIT_UTILITY_SHA=$GIT_UTILITY_SHA"
echo "STATIC_IP=$STATIC_IP"

for k8sResource in $INPUT_DIR/*.yaml; do
    # envsubst reads the input file, replaces any ENV variables (not shell variables)
    # and writes the output file to the > "file"
    # this has the side effect of being our 'copy all files to output dir'
    envsubst < $k8sResource > "$OUTPUT_DIR/$(basename $k8sResource)"
done