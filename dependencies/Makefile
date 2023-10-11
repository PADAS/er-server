#
# Makefile for managing our python requirements as based on the following article
# http://jamescooke.info/a-successful-pip-tools-workflow-for-managing-python-package-requirements.html
#
#

.PHONY: all check clean

PIP_COMPILE_FLAGS=-v --resolver=backtracking --find-links=wheelhouse

all: requirements.txt requirements-dev.txt requirements-docs.txt

requirements.txt: requirements.in requirements-pinned.txt
	pip-compile $(PIP_COMPILE_FLAGS) --output-file=$@ $^

requirements-dev.txt: requirements.txt requirements-dev.in
	pip-compile $(PIP_COMPILE_FLAGS) --output-file=$@ $^

requirements-docs.txt: requirements-docs.in
	pip-compile $(PIP_COMPILE_FLAGS) --output-file=$@ $^

check:
	@which pip-compile > /dev/null

clean: check
	$(RM) requirements.txt requirements-dev.txt requirements-docs.txt
