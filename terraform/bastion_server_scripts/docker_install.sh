#!/bin/bash
sudo apt-get update
sudo apt install -y apt-transport-https ca-certificates curl gnupg2 software-properties-common
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
