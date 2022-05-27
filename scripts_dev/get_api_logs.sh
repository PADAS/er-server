LIST_PODS=$(kubectl -n development get pods | grep "^api-")
API_POD=$(cut -d' ' -f1 <<< $LIST_PODS)
echo "Getting logs of pod $API_POD"
kubectl -n development logs $API_POD -c das-api -f
