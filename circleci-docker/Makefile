MAKEFLAGS += --warn-undefined-variables

.POSIX:
SHELL := /usr/bin/env sh

.DEFAULT_GOAL := help

base_image_name := gcr.io/padas-app/circleci/das-base
tag ?= tag-not-provided-$(shell date +%s)

server_semver_stem := $(shell cat $(CURDIR)/../SERVER_VERSION)
web_semver_stem := $(shell cat $(CURDIR)/../WEB_VERSION)
semver_metadata_suffix ?= beta-$(shell date +%s)
server_full_semver ?= $(server_semver_stem)-$(semver_metadata_suffix)
web_full_semver ?= $(web_semver_stem)-$(semver_metadata_suffix)

manifest_file := GENERATED_MANIFEST
server_manifest_key := SERVER_VERSION
web_manifest_key := WEB_VERSION
manifest_wip_file := $(manifest_file).local
manifest_path := $(CURDIR)/../

.PHONY: help
help: ## show this help
	@ printf "\033[36m%-20s\033[0m %-50s \033[93m%s\033[0m\n" "target" "description" "arguments"
	@ printf "%s\n" "------------------------------------------------------------------------------------------------------------------"
	@ grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## |\| "}; {printf "\033[36m%-20s\033[0m %-50s \033[93m%s\033[0m\n", $$1, $$2, $$3}' >&2

.PHONY: base_build_and_push
base_build_and_push: ## Develop branch: Build the Docker base image and push to Google Container Repository with unique tag ids
	cd ../ && docker build  -f circleci-docker/base/Dockerfile --tag $(base_image_name):$(tag) .
	docker push $(base_image_name):$(tag)

earthranger_api_image_name := gcr.io/padas-app/circleci/earthranger-api

.PHONY: earthranger_api_build_and_push
earthranger_api_build_and_push: ## Develop branch: Build the Docker EarthRanger API image and push to Google Container Repository with unique tag ids
	cd ../ && docker build  -f circleci-docker/Dockerfile --tag $(earthranger_api_image_name):$(tag) .
	docker push $(earthranger_api_image_name):$(tag)

.PHONY: generate_manifest
generate_manifest: semver_metadata_suffix ?=
generate_manifest:
	printf "%s = \"%s\"""\n%s = \"%s\"" "$(server_manifest_key)" "$(server_full_semver)" "$(web_manifest_key)" "$(web_full_semver)" > "$(manifest_path)$(manifest_wip_file)"

.PHONY: commit_and_push_manifest
commit_and_push_manifest: # this should only be run by the build server
	git diff --quiet --exit-code || (printf "\nthere are uncommitted changes... will not commit manifest\n" >&2; exit 1) && \
	cp $(manifest_path)$(manifest_wip_file) $(manifest_path)$(manifest_file) && \
	if git diff --exit-code $(manifest_path)$(manifest_file); then (printf "\nno changes to the manifest... nothing to do\n" >&2; exit 0); else git add $(manifest_path)$(manifest_file) && git commit -m '[ci skip] robo-bump manifest' && git push && echo 'successful push';fi
