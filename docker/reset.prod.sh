#!/usr/bin/env b#!/bin/bash

COMMAND=$@
docker-compose stop $COMMAND
docker-compose rm -f $COMMAND
docker-compose up -d $COMMAND
docker-compose logs -f $COMMANDash