MAKEFLAGS += --warn-undefined-variables

minimum_version := 4.1
current_version := $(MAKE_VERSION)

ifneq ($(minimum_version), $(firstword $(sort $(current_version) $(minimum_version))))
$(error You need GNU make version $(minimum_version) or greater. You have $(current_version))
endif

.POSIX:
SHELL := /bin/sh

.DEFAULT_GOAL := help

uname_s := $(shell uname -s)

vulcan_path := $(dir $(lastword $(MAKEFILE_LIST))).vulcan

coerced_path_for_terraform := $(vulcan_path)/$(uname_s):$(shell dirname "$$(which git)")

terraform_version := 0.13.7
terraform_path := $(vulcan_path)/$(uname_s)
terraform_binary := $(terraform_path)/terraform
terraform_zip := $(terraform_path)/terraform_$(terraform_version)_$(uname_s)_amd64.zip

.PHONY: help
help:
	@ printf "This is meant to be used as a submodule or subtree in other git repos rather than run directly.\n" >&2

.PHONY: terraform_version
terraform_version: $(terraform_binary)
	export PATH="$(coerced_path_for_terraform)" && terraform version

.PHONY: terraform_fmt
terraform_fmt: fmt_dir ?=
terraform_fmt: fmt_options ?=
terraform_fmt: $(terraform_binary)
	export PATH="$(coerced_path_for_terraform)" && terraform fmt $(fmt_options) $(fmt_dir)

.PHONY: terraform_init
terraform_init: init_dir ?=
terraform_init: init_options ?=
terraform_init: $(terraform_binary)
	export PATH="$(coerced_path_for_terraform)" && terraform init $(init_options) $(init_dir)

.PHONY: terraform_plan
terraform_plan: plan_dir ?=
terraform_plan: plan_options ?=
terraform_plan: $(terraform_binary)
	export PATH="$(coerced_path_for_terraform)" && terraform plan $(plan_options) $(plan_dir)

.PHONY: terraform_apply
terraform_apply: apply_dir_or_planfile ?=
terraform_apply: apply_options ?=
terraform_apply: $(terraform_binary)
	export PATH="$(coerced_path_for_terraform)" && terraform apply $(apply_options) $(apply_dir_or_planfile)

.PHONY: terraform_output
terraform_output: output_name ?=
terraform_output: output_options ?=
terraform_output: $(terraform_binary)
	@export PATH="$(coerced_path_for_terraform)" && terraform output $(output_options) $(output_name)

.PHONY: terraform_workspace
terraform_workspace: workspace_dir ?=
terraform_workspace: workspace_name ?=
terraform_workspace: workspace_options ?=
terraform_workspace: workspace_subcommand ?=
terraform_workspace: $(terraform_binary)
	@ if [ -z "$(workspace_subcommand)" ]; then (printf "\nYou must provide a \033[31mterraform workspace\033[0m subcommand as \033[93mworkspace_subcommand\033[0m\n\n" >&2 ; exit 1); fi
	@ if [ \( "$(workspace_subcommand)" = show \) -a \( -n "$(workspace_dir)" -o -n "$(workspace_name)" -o -n "$(workspace_options)" \) ]; then (printf "\nYou cannot specify \033[93mworkspace_dir\033[0m or \033[93mworkspace_name\033[0m or \033[93mworkspace_options\033[0m with \033[93mworkspace_command\033[0m=show\n\n" >&2; exit 1); fi
	@ if [ \( "$(workspace_subcommand)" = list \) -a \( -n "$(workspace_name)" -o -n "$(workspace_options)" \) ]; then (printf "\nYou cannot specify \033[93mworkspace_name\033[0m or \033[93mworkspace_options\033[0m with \033[93mworkspace_command\033[0m=list\n\n" >&2; exit 1); fi
	@ if [ \( "$(workspace_subcommand)" = select \) -a \( -n "$(workspace_options)" \) ]; then (printf "\nYou cannot specify \033[93mworkspace_options\033[0m with \033[93mworkspace_command\033[0m=select\n\n" >&2; exit 1); fi
	export PATH="$(coerced_path_for_terraform)" && terraform workspace $(workspace_subcommand) $(workspace_options) $(workspace_name) $(workspace_dir)

.PHONY: terraform_destroy
terraform_destroy: destroy_dir ?=
terraform_destroy: destroy_options ?=
terraform_destroy: $(terraform_binary)
	@ export PATH="$(coerced_path_for_terraform)" && printf "This will destroy *all* things in the Terraform workspace: '%s'\n" "$$(terraform workspace show)" >&2
	@ export RESPONSE="$$(read -p "You must type exactly 'yes' to proceed: " -r RESPONSE; echo $${RESPONSE})" && if [ "$$RESPONSE" != "yes" ]; then ( printf "You typed '%s'... bailing out!\n" "$$RESPONSE" >&2 ; exit 1); fi
	export PATH="$(coerced_path_for_terraform)" && terraform destroy $(destroy_options) $(destroy_dir)

$(terraform_binary): $(terraform_zip)
	@ if command -p -V unzip; then unzip -o -DD $(terraform_zip) -d $(terraform_path); \
		else gunzip --stdout <$(terraform_zip) > $(terraform_binary) && chmod +x $(terraform_binary); fi
