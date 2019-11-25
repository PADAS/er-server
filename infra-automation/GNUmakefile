this_file := $(lastword $(MAKEFILE_LIST))
MAKEFLAGS += --warn-undefined-variables

minimum_version := 4.1
current_version := $(MAKE_VERSION)

ifneq ($(minimum_version), $(firstword $(sort $(current_version) $(minimum_version))))
$(error You need GNU make version $(minimum_version) or greater. You have $(current_version))
endif

.POSIX:
SHELL := /bin/sh

.DEFAULT_GOAL := help

vulcan_path := $(CURDIR)/.vulcan
terraform_makefile := $(vulcan_path)/terraform-subtree/GNUmakefile
vault_makefile := $(vulcan_path)/vault-subtree/GNUmakefile

terraform_path := $(CURDIR)/../terraform
template_path := $(CURDIR)/../templated-deployment
tfvars_overrides := $(template_path)/tfvars-overrides

.PHONY: help
help: ## show this help
	@ printf "\033[36m%-20s\033[0m%-50s\033[93m%-35s\033[92m%s\033[0m\n" "target" "description" "arguments" "defaults" >&2
	@ printf "%s\n" "------------------------------------------------------------------------------------------------------------------------------------" >&2
	@ grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk -F ":.*?## |[\|] " '{printf "\033[36m%-20s\033[0m%-50s\033[93m%-35s\033[92m%s\033[0m\n", $$1, $$2, $$3, $$4}' >&2

.PHONY: configure_dev
configure_dev: ## configure your workstation for fun and profit
	git config core.hooksPath .vulcan/git-hooks-subtree

.PHONY: tf_fmt
tf_fmt: ## terraform fmt -recursive on the directory
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_fmt fmt_options="-recursive"

.PHONY: tf_init
tf_init: init_options ?=
tf_init: ## terraform init
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_init init_options=$(init_options)

.PHONY: tf_workspace_list
tf_workspace_list: ## terraform workspace list
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_workspace workspace_subcommand=list

.PHONY: tf_workspace_select
tf_workspace_select: workspace ?=
tf_workspace_select: ## terraform workspace select | workspace="WORKSPACE"
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_workspace workspace_subcommand=select workspace_name=$(workspace)

.PHONY: tf_workspace_new
tf_workspace_new: workspace ?=
tf_workspace_new: ## terraform workspace new | workspace="WORKSPACE"
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_workspace workspace_subcommand=new workspace_name=$(workspace)

.PHONY: tf_plan
tf_plan: plan_options ?=
tf_plan: ## terraform plan | [plan_options="ARGS"]
	@ $(MAKE) --no-print-directory --file $(vault_makefile) vault_login
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_plan plan_options="$(plan_options)"

.PHONY: tf_apply
tf_apply: apply_dir_or_planfile ?=
tf_apply: apply_options ?=
tf_apply: ## terraform apply | [apply_options="ARGS"] [apply_dir_or_planfile="PATH"]
	@ $(MAKE) --no-print-directory --file $(vault_makefile) vault_login
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_apply apply_dir_or_planfile="$(apply_dir_or_planfile)" apply_options="$(apply_options)"

.PHONY: tf_output
tf_output: output_name ?=
tf_output: ## terraform output | [output_name="NAME"]
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_output output_name="$(output_name)"

.PHONY: tf_version
tf_version: ## show terraform version
	@ $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_version

.PHONY: render_templates
render_templates: tfvars_environment ?= no_overrides
render_templates: ## render templates (using Terraform) | [tfvars_environment="BRANCH_NAME"]
	@ cd $(template_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_init
	@ if [ ! -f $(tfvars_overrides)/$(tfvars_environment).tfvars ]; then touch $(tfvars_overrides)/$(tfvars_environment).tfvars; fi
	@ cd $(template_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_apply apply_options="-auto-approve -var-file='$(tfvars_overrides)/$(tfvars_environment).tfvars'"
	@ cat $(template_path)/rendered/api-deployment.yaml


commit_message_path := $(CURDIR)/.robo-commit-message

# Todo: Retrofit this before merging to master
legacy_concourse_shim_gcr := gcr.io/padas-app/circleci/earthranger-api

gcr_root := gcr.io/padas-app/circleci/deleteme
manifest_file := $(CURDIR)/../GENERATED_MANIFEST
manifest_key := SERVER_VERSION
server_semver_file := $(CURDIR)/../SERVER_VERSION
web_semver_file := $(CURDIR)/../WEB_VERSION

current_branch := $(shell echo "$$(git rev-parse --quiet --verify --abbrev-ref HEAD || exit 1)")
descriptive_server_gcr_path := $(gcr_root)/$(shell echo $(current_branch) | sed 's/[^/A-Za-z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]' || exit 1)
descriptive_gcr_path_stem := $(shell git config --get user.name || exit 1)

.PHONY: build_and_push
build_and_push: descriptive_gcr_path_stem := $(shell git config --get user.name || exit 1)
build_and_push: descriptive_server_gcr_path := $(gcr_root)/$(shell echo $(descriptive_gcr_path_stem) | sed 's/[^/A-Za-z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]' || exit 1)
build_and_push: latest_gcr_tag := latest
build_and_push: semver_gcr_tag := $(shell cat "$(server_semver_file)" || exit 1)
build_and_push: sha_gcr_tag := $(shell git rev-parse --quiet --verify HEAD || exit 1)
build_and_push: unique_gcr_tag := $(shell date +%s || exit 1)
build_and_push: ## build and push
	@ if [ -z "$(semver_gcr_tag)" ]; then (printf "\e[31m\tCould not resolve semver_gcr_tag by cat'ing '$(server_semver_file)'.\e[0m\n" >&2; exit 1); fi
	@ if [ -z "$(sha_gcr_tag)" ]; then (printf "\e[31m\tCould not resolve sha_gcr_tag with git rev-parse.\e[0m\n" >&2; exit 1); fi
	@ if [ -z "$(unique_gcr_tag)" ]; then (printf "\e[31m\tCould not resolve unique_gcr_tag with 'date'.\e[0m\n" >&2; exit 1); fi
	@ if [ "$$(dirname $(descriptive_server_gcr_path))" = "$$(dirname $(gcr_root))" ]; then (printf "\e[31m\tCould not construct a unique, sanitized GCR path.\e[0m\n" >&2; exit 1); fi
	docker build --tag $(descriptive_server_gcr_path):$(latest_gcr_tag) --tag $(descriptive_server_gcr_path):$(semver_gcr_tag) --tag $(descriptive_server_gcr_path):$(sha_gcr_tag) --tag $(descriptive_server_gcr_path):$(unique_gcr_tag) .
	docker push $(descriptive_server_gcr_path):$(latest_gcr_tag)
	docker push $(descriptive_server_gcr_path):$(semver_gcr_tag)
	docker push $(descriptive_server_gcr_path):$(sha_gcr_tag)
	docker push $(descriptive_server_gcr_path):$(unique_gcr_tag)


.PHONY: generate_manifest
generate_manifest: ## remove and regenerate the manifest
	@ rm -f "$(manifest_file)"
	@ $(MAKE) --no-print-directory -f $(this_file) $(manifest_file)

.PHONY: commit_and_push_manifest
commit_and_push_manifest: $(manifest_file) # this should only be run by the build server
	git diff --cached --quiet --exit-code || (printf "\tThere are staged, uncommitted changes... will not commit manifest.\n" >&2; exit 1)
	if git diff --exit-code $(manifest_file); then (printf "\tNo changes to the manifest... nothing to do.\n" >&2; exit 0); else git add $(manifest_file) && git commit -F $(commit_message_path) && git push; fi

$(manifest_file):
	@ printf "\e[31m\tGenerating new manifest.\e[0m\n" >&2
	@ $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(descriptive_server_gcr_path)" manifest_key="$(manifest_key)" > /dev/null 2>&1 || (printf "\e[31m\tFailed to find 'latest' tagged image at '$(descriptive_server_gcr_path)'.\e[0m\n" >&2; exit 1)

.PHONY: append_to_manifest
append_to_manifest: gcr_path :=
append_to_manifest: manifest_key :=
append_to_manifest: # this should only be run by the build server
	@ export DIGEST="$$(gcloud container images list-tags $(gcr_path) --filter="tags:latest" --format="value(Digest)" || exit 1)" && \
		if [ -n "$$DIGEST" ]; then printf "%s = \"%s@%s\"\n" "$(manifest_key)" "$(gcr_path)" "$$DIGEST" >> $(manifest_file); else exit 1; fi
