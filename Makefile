default: restart-deploy

NAMESPACE=development
POD=

TEST_PATH=
TEST_CLASS=
TEST_METHOD=

restart-deploy:
	kubectl -n ${NAMESPACE} rollout restart deploy api

get-pods:
	kubectl -n ${NAMESPACE} get pods

watch-pods:
	watch kubectl -n ${NAMESPACE} get pods

get-api-pod:
	kubectl -n ${NAMESPACE} get pods | grep "^api-"

get-api-logs:
	kubectl -n ${NAMESPACE} logs ${POD} -c das-api -f

connect-api:
	kubectl -n ${NAMESPACE} exec -ti deploy/api -- bash

connect-db:
	kubectl -n ${NAMESPACE} exec -it ${DB_POD} -- psql -U postgres

test:
	python -m pytest -vv ${TEST_PATH}::${TEST_CLASS}::${TEST_METHOD} --no-migrations

test-class:
	python -m pytest -vv ${TEST_PATH}::${TEST_CLASS} --no-migrations

format-file:
	./formatter_py_files.sh ${FILE}
