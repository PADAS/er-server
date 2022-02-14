default: restart-deploy

NAMESPACE=development

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

clean-pods:
	kubectl -n ${NAMESPACE} delete pod -l das.configuration=server

connect-api:
	kubectl -n ${NAMESPACE} exec -ti deploy/api -- bash

connect-db:
	kubectl -n ${NAMESPACE} exec -it ${DB_POD} -- psql -U postgres

test:
	pytest -vv ${TEST_PATH}::${TEST_CLASS}::${TEST_METHOD}

test-class:
	pytest -vv ${TEST_PATH}::${TEST_CLASS}

format-file:
	./formatter_py_files.sh ${FILE}

check-requirements:
	safety check -r dependencies/requirements.txt

make check-requirements-dev:
	safety check -r dependencies/requirements-dev.txt
