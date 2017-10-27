#!/usr/bin/env bash

# /usr/local/bin/virtualenv ./depends; source ./depends/bin/activate
export PROJECT_DIR=$PWD
if [!-d $PROJECT_DIR]; then /usr/local/bin/virtualenv $PROJECT_DIR/depends; fi; source $PROJECT_DIR/depends/bin/activate
pip install requests==2.18.4

zip -g $PROJECT_DIR/panthera-camera-trap.zip
zip -g $PROJECT_DIR/panthera-camera-trap.zip panthera-camera-trap.py settings.py
cd $PROJECT_DIR/depends/lib/site-packages
zip -r9 -g $PROJECT_DIR/panthera-camera-trap.zip *
cd $PROJECT_DIR
