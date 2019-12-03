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
	@ cd $(template_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_apply apply_options="-auto-approve -var-file='$(tfvars_overrides)/$(tfvars_environment).tfvars' -var kubernetes_namespace=OUTPUT HERE"
	@ cat $(template_path)/rendered/api-deployment.yaml
