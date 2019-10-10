MAKEFLAGS += --warn-undefined-variables

.POSIX:
SHELL := /usr/bin/env sh

.DEFAULT_GOAL := help

uname_s := $(shell uname -s)
vulcan_path := $(CURDIR)/.vulcan

.PHONY: help
help: ## show this help
	@ printf "\033[36m%-20s\033[0m %-50s \033[93m%s\033[0m\n" "target" "description" "arguments"
	@ printf "%s\n" "------------------------------------------------------------------------------------------------------------------"
	@ grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## |\| "}; {printf "\033[36m%-20s\033[0m %-50s \033[93m%s\033[0m\n", $$1, $$2, $$3}' >&2

.PHONY: terraform_fmt
terraform_fmt: ## invoke (bundled) Terraform fmt -recursive
	@ export PATH="$(vulcan_path)/$(uname_s):$${PATH}" && terraform fmt -recursive
	@ printf "%s\n" "done formatting" >&2

.PHONY: terraform_init
terraform_init: ## invoke (bundled) Terraform init
	@ export PATH="$(vulcan_path)/$(uname_s):$${PATH}" && terraform init

.PHONY: terraform_plan
terraform_plan: plan_args ?=
terraform_plan: ## invoke (bundled) Terraform plan | [plan_args="..."]
	@ export PATH="$(vulcan_path)/$(uname_s):$${PATH}" && terraform plan $(plan_args)

.PHONY: terraform_apply
terraform_apply: apply_args ?=
terraform_apply: ## invoke (bundled) Terraform apply | [apply_args="..."]
	@ git diff --quiet --exit-code || (printf "%s\n" "there are unstaged changes... it is not wise to run terraform apply" >&2; exit 1)
	@ git diff --cached --quiet --exit-code || (printf "%s\n" "there are uncommitted changes... it is not wise to run terraform apply" >&2; exit 1)
	@ export PATH="$(vulcan_path)/$(uname_s):$${PATH}" && terraform apply $(apply_args)
	@ printf "\n\033[1;4;5;31;107m%s\033[0m\n" "make sure to git push any commits back to origin" >&2

.PHONY: terraform_workspace_select
terraform_workspace_select: workspace ?= dev
terraform_workspace_select: ## invoke (bundled) Terraform workspace select on extant workspace | [workspace="WORKSPACE"] | workspace="dev"
	@ export PATH="$(vulcan_path)/$(uname_s):$${PATH}" && terraform workspace select $(workspace)


