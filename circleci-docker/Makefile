MAKEFLAGS += --warn-undefined-variables

.POSIX:
SHELL := /usr/bin/env sh

.DEFAULT_GOAL := help

base_image_name := gcr.io/padas-app/deleteme/circleci-das-base
version ?= beta-$(shell date +%s)

.PHONY: help
help: ## show this help
	@ printf "\033[36m%-20s\033[0m %-50s \033[93m%s\033[0m\n" "target" "description" "arguments"
	@ printf "%s\n" "------------------------------------------------------------------------------------------------------------------"
	@ grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## |\| "}; {printf "\033[36m%-20s\033[0m %-50s \033[93m%s\033[0m\n", $$1, $$2, $$3}' >&2

.PHONY: base_build_and_push
base_build_and_push: ## Develop branch: Build the Docker base image and push to Google Container Repository with unique tag ids
	cd base && docker build --tag $(base_image_name):$(version) .
	docker push $(base_image_name):$(version)
