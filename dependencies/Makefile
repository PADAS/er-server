#
# Makefile for managing our python requirements as based on the following article
# http://jamescooke.info/a-successful-pip-tools-workflow-for-managing-python-package-requirements.html
#
#

.PHONY: all check clean

objects = $(wildcard *.in)
outputs := $(objects:.in=.txt)

all: $(outputs)

%.txt: %.in
	pip-compile -v --output-file $@ $<

requirements-ci.txt: requirements.txt

requirements-dev.txt: requirements.txt

check:
	@which pip-compile > /dev/null

clean: check
	- rm *.txt