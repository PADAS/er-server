#!/bin/bash
# post cluster creatuon, assign a static address. 
# Suggested manual workflow:
#  - stand up cluster
#  - kubectl get services -n <pipeline name>
#  - get the nginx external address
#  - use this script to populate that ip address using the cluster (not the pipeline name)
#  - modify das-static-ip to the static ip
if [ $# -ne 2 ]
  then
    echo "Usage $0 cluster-name pipeline-name"
    exit 1
fi
AKS_CLUSTER=$1
AKS_PIPELINE=$2
VM_INSTANCE=`eval /usr/local/bin/az aks show --resource-group DAS-Dev --name ${AKS_CLUSTER} --query nodeResourceGroup -o tsv`
echo "VM instance is $VM_INSTANCE"
STATIC_ADDRESS=`eval az network public-ip create \
    --resource-group ${VM_INSTANCE} \
    --name ${AKS_PIPELINE}-${AKS_CLUSTER}-static-ip \
    --allocation-method static`
echo "Reserved ${STATIC_ADDRESS} with resource name ${AKS_PIPELINE}-${AKS_CLUSTER}-static-ip"
echo "Assign this address to the das-static-ip in your /ci/params/${AKS_PIPELINE}.params.yaml file"
