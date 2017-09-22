#!/bin/bash -e

###################################################################################
#
# This script is meant to be run from other scripts that need to login to concourse with fly
#
###################################################################################

function login_to_concourse()
{
    fly -t $PROJECT login -c https://35.197.64.22 -k -u vulcan -p onlyat
}


# used in set.pipeline for a given project to generate default values for setting varibable files with fly
function set_var_file_if_exists()
{
    local VAR_FILE=$1
    if [ -e $VAR_FILE ]; then
        echo "-l$VAR_FILE"
    else
        echo ""
    fi
}
