#!/bin/bash

command=$@

if [[ -n "$command" ]]; then
    docker exec -it das_api python3 /var/www/das/manage.py $command --settings=das_server.local_settings    
else
    echo "argument error"
fi