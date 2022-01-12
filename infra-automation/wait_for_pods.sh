#!/usr/bin/env bash

set -e

function __is_pod_ready() {
  [[ "$(kubectl get po "$1" -n $2 -o 'jsonpath={.status.conditions[?(@.type=="Ready")].status}')" == 'True' ]]
}

function __pods_ready() {
  local pod
  local pods
  local namespace

  pods=$1
  namespace=$2

  echo $pods
  echo $namespace

  [[ "$#" == 0 ]] && return 0

  for pod in $pods; do
    __is_pod_ready "$pod" "$namespace" || return 1
  done

  return 0
}

function __wait-until-pods-ready() {
  local period interval i pods namespace

  if [[ $# != 3 ]]; then
    echo "Usage: wait-until-pods-ready PERIOD INTERVAL" >&2
    echo "" >&2
    echo "This script waits for all pods to be ready in the current namespace." >&2

    return 1
  fi

  period="$1"
  interval="$2"
  namespace="$3"

  for ((i=0; i<$period; i+=$interval)); do
    pods="$(kubectl get po -n $namespace -o 'jsonpath={.items[*].metadata.name}')"
    if __pods_ready $pods $namespace; then
      return 0
    fi

    echo "Waiting for pods to be ready..."
    sleep "$interval"
  done

  echo "Waited for $period seconds, but all pods are not ready yet."
  return 1
}

__wait-until-pods-ready $@
