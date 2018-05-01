#!/bin/bash
PROMETHEUS_URL=$1

curl -i -XPOST "http://admin:admin@localhost:3000/api/datasources" \
    -H "Content-Type: application/json;charset=UTF-8" \
    --data-binary "{\"name\":\"Prometheus\",\"type\":\"prometheus\",\"access\":\"proxy\",\"url\":\"$PROMETHEUS_URL\"}"