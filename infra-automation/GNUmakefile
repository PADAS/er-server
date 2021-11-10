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

terraform_path := $(CURDIR)/../terraform
template_path := $(CURDIR)/../templated-deployment
tfvars_overrides := $(template_path)/tfvars-overrides

rendered_template_path := $(CURDIR)/../templated-deployment/rendered

.PHONY: help
help: ## show this help
	@ printf "\033[36m%-32s\033[0m%-50s\033[93m%-35s\033[92m%s\033[0m\n" "target" "description" "arguments" "defaults" >&2
	@ printf "%s\n" "------------------------------------------------------------------------------------------------------------------------------------" >&2
	@ grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk -F ":.*?## |[\|] " '{printf "\033[36m%-32s\033[0m%-50s\033[93m%-35s\033[92m%s\033[0m\n", $$1, $$2, $$3, $$4}' >&2

.PHONY: configure_dev
configure_dev: ## configure your workstation for fun and profit
	git config core.hooksPath .vulcan/git-hooks-subtree

.PHONY: tf_fmt
tf_fmt: ## terraform fmt -recursive on the directory
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_fmt fmt_options="-recursive"
	@ cd $(template_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_fmt fmt_options="-recursive"

.PHONY: tf_init
tf_init: init_options ?=
tf_init: ## terraform init
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_init init_options=$(init_options)

.PHONY: tf_workspace_delete
tf_workspace_delete: workspace ?=
tf_workspace_delete: ## terraform workspace delete | workspace="WORKSPACE"
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_workspace workspace_subcommand=delete workspace_name=$(workspace)

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
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_plan plan_options="$(plan_options)"

.PHONY: tf_apply
tf_apply: apply_dir_or_planfile ?=
tf_apply: apply_options ?=
tf_apply: ## terraform apply | [apply_options="ARGS"] [apply_dir_or_planfile="PATH"]
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_apply apply_dir_or_planfile="$(apply_dir_or_planfile)" apply_options="$(apply_options)"

.PHONY: tf_destroy
tf_destroy: destroy_dir ?=
tf_destroy: ## terraform destroy | [destroy_dir="PATH"]
	@ cd $(terraform_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_destroy destroy_dir="$(destroy_dir)"

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
	@ K8S_NAMESPACE=$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="kubernetes_namespace") && \
	DATABASE_NAME=$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="database_name") && \
	SITE_IP_ADDRESS=$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="site_ip_address") && \
	GS_BUCKET_NAME=$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="user_uploads_bucket_name") && \
	APP_INFRA_WORKSPACE=$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="app_infra_workspace") && \
	FQDN=$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="fqdn") && \
	cd $(template_path) && $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_apply \
	 apply_options="-auto-approve -var-file='$(tfvars_overrides)/$(tfvars_environment).tfvars' \
	 -var app_infra_workspace=$$APP_INFRA_WORKSPACE \
	 -var kubernetes_namespace=$$K8S_NAMESPACE \
	 -var site_terraform_workspace=$(tfvars_environment) \
       	 -var db_name=$$DATABASE_NAME \
	 -var site_ip_address=$$SITE_IP_ADDRESS \
	 -var fqdn=$$FQDN \
	 -var gs_bucket_name=$$GS_BUCKET_NAME"
	@ cat $(template_path)/rendered/circleci-01-server-configmap.yaml

.PHONY: kubectl_apply
kubectl_apply: ## kubectl apply (recursively) everything in the ./k8s path
	kubectl apply --recursive --filename="$(CURDIR)/../templated-deployment/rendered"

.PHONY: database_init
database_init: tfvars_environment ?= no_overrides
database_init: ## Initialize a feature site database | [tfvars_environment="BRANCH_NAME"]
	@ $$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="gcloud_kubectl_configuration" || false) && \
	ALLOWED_IP_ADDRESS=$$($(CURDIR)/get_cidr_blocks.sh) && \
	CONTAINER_IP_ADDRESS=$$(curl --silent ifconfig.me)/32 && \
	K8S_NAMESPACE=$$(echo "$(tfvars_environment)" | tr '[:upper:]' '[:lower:]') && \
	gcloud container clusters update das-dev \
	  --enable-master-authorized-networks \
	  --zone us-west1-a \
	  --master-authorized-networks $$CONTAINER_IP_ADDRESS,$$ALLOWED_IP_ADDRESS && \
	K8S_POD=$$(kubectl get pods -n $$K8S_NAMESPACE --selector=das.component=api -o jsonpath='{.items[*].metadata.name}') && \
	$(CURDIR)/wait_for_pods.sh 120 6 && \
	echo $$K8S_NAMESPACE && \
	echo $$K8S_POD && \
	kubectl version && \
	kubectl -n $$K8S_NAMESPACE exec -it $$K8S_POD -c das-api -- start_scripts/start_load_initial_data_tests.sh && \
	gcloud container clusters update das-dev \
	  --enable-master-authorized-networks \
	  --zone us-west1-a \
	  --master-authorized-networks $$ALLOWED_IP_ADDRESS

.PHONY: kubectl_apply_via_proxy
kubectl_apply_via_proxy: # this should only be run by the build server
	$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="gcloud_kubectl_configuration" || false)
	kubectl config set-cluster "$$(kubectl config get-clusters | tail -n 1)" --server="https://$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="cluster_proxy_endpoint")" || false
	echo "$$($(MAKE) --no-print-directory --silent -f $(this_file) tf_output output_name="cluster_b64_encoded_proxy_ca_certificate")" | base64 -d > proxy.crt
	kubectl config set-cluster "$$(kubectl config get-clusters | tail -n 1)" --certificate-authority="./proxy.crt" || false
	for file in $$(find "$(rendered_template_path)" -type f |grep circleci-| sort); do sleep 1 && kubectl apply --filename "$$file"; done;
	# kubectl apply --filename "$(rendered_template_path)/circleci-api-deployment.yaml"

commit_message_path := $(CURDIR)/.robo-commit-message

manifest_file := $(CURDIR)/../GENERATED_MANIFEST

# Server
server_manifest_key := SERVER_VERSION
gcr_root := gcr.io/padas-app/circleci/das-server
server_default_branch := develop
server_gcr_path_default_branch := $(gcr_root)/$(server_default_branch)
server_semver_file := $(CURDIR)/../SERVER_VERSION

web_react_manifest_key := WEB_REACT_VERSION
gcr_web_react_root := gcr.io/padas-app/circleci/das-web-react
web_react_default_branch := develop
web_react_gcr_path_default_branch := $(gcr_web_react_root)/$(web_react_default_branch)

web_admin_manifest_key := WEB_ADMIN_VERSION
gcr_web_admin_root := gcr.io/padas-app/circleci/das-react-admin
web_admin_default_branch := master
web_admin_gcr_path_default_branch := $(gcr_web_admin_root)/$(web_admin_default_branch)

ingress_manifest_key := INGRESS_VERSION
gcr_ingress_root := gcr.io/padas-app/circleci/das-ingress
ingress_default_branch := develop
ingress_gcr_path_default_branch := $(gcr_ingress_root)/$(ingress_default_branch)

current_branch := $(shell echo "$$(git rev-parse --quiet --verify --abbrev-ref HEAD || exit 1)")
descriptive_server_gcr_path := $(gcr_root)/$(shell echo $(current_branch) | sed 's/[^/A-Za-z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]' || exit 1)
descriptive_web_react_gcr_path := $(gcr_web_react_root)/$(shell echo $(current_branch) | sed 's/[^/A-Za-z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]' || exit 1)
descriptive_web_admin_gcr_path := $(gcr_web_admin_root)/$(shell echo $(current_branch) | sed 's/[^/A-Za-z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]' || exit 1)
descriptive_ingress_gcr_path := $(gcr_ingress_root)/$(shell echo $(current_branch) | sed 's/[^/A-Za-z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]' || exit 1)


.PHONY: build_and_push
build_and_push: latest_gcr_tag := latest
build_and_push: semver_gcr_tag := $(shell cat "$(server_semver_file)" || exit 1)
build_and_push: sha_gcr_tag := $(shell git rev-parse --quiet --verify HEAD || exit 1)
build_and_push: unique_gcr_tag := $(shell date +%s || exit 1)
build_and_push: build_number   := 0
build_and_push: ## build and push
	@ if [ -z "$(semver_gcr_tag)" ]; then (printf "\e[31m\tCould not resolve semver_gcr_tag by cat'ing '$(server_semver_file)'.\e[0m\n" >&2; exit 1); fi
	@ if [ -z "$(sha_gcr_tag)" ]; then (printf "\e[31m\tCould not resolve sha_gcr_tag with git rev-parse.\e[0m\n" >&2; exit 1); fi
	@ if [ -z "$(unique_gcr_tag)" ]; then (printf "\e[31m\tCould not resolve unique_gcr_tag with 'date'.\e[0m\n" >&2; exit 1); fi
	@ if [ "$$(dirname $(descriptive_server_gcr_path))" = "$$(dirname $(gcr_root))" ]; then (printf "\e[31m\tCould not construct a unique, sanitized GCR path.\e[0m\n" >&2; exit 1); fi
	cd $(CURDIR)/.. \
	&& echo BUILD_NUMBER = $(build_number) > das/das_server/version.py \
	&& docker build  -f circleci-docker/Dockerfile --tag $(descriptive_server_gcr_path):$(latest_gcr_tag) --tag $(descriptive_server_gcr_path):$(semver_gcr_tag) --tag $(descriptive_server_gcr_path):$(sha_gcr_tag) --tag $(descriptive_server_gcr_path):$(unique_gcr_tag) .
	docker push $(descriptive_server_gcr_path):$(latest_gcr_tag)
	docker push $(descriptive_server_gcr_path):$(semver_gcr_tag)
	docker push $(descriptive_server_gcr_path):$(sha_gcr_tag)
	docker push $(descriptive_server_gcr_path):$(unique_gcr_tag)

.PHONY: generate_manifest
generate_manifest: ## remove and regenerate the manifest
	@ rm -f "$(manifest_file)"
	@ $(MAKE) --no-print-directory -f $(this_file) $(manifest_file)
	@ echo "" && cat $(manifest_file) && echo ""

.PHONY: commit_and_push_manifest
commit_and_push_manifest: $(manifest_file) # this should only be run by the build server
	git diff --cached --quiet --exit-code || (printf "\tThere are staged, uncommitted changes... will not commit manifest.\n" >&2; exit 1)
	if git diff --exit-code $(manifest_file); then (printf "\tNo changes to the manifest... nothing to do.\n" >&2; exit 0); else git add $(manifest_file) && git commit -F $(commit_message_path) && git push; fi

$(manifest_file):
	@ printf "\e[31m\tGenerating new manifest.\e[0m\n" >&2
	@ $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(descriptive_server_gcr_path)" \
	       	manifest_key="$(server_manifest_key)" > /dev/null 2>&1 \
	       	|| $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(server_gcr_path_default_branch)" \
	       	manifest_key="$(server_manifest_key)" > /dev/null 2>&1 || \
		(printf "\e[31m\tFailed to find latest tagged image at '$(descriptive_server_gcr_path)'.\e[0m\n" >&2; exit 1)

	@ $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(descriptive_web_react_gcr_path)" \
	       	manifest_key="$(web_react_manifest_key)" > /dev/null 2>&1 \
	       	|| $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(web_react_gcr_path_default_branch)" \
	       	manifest_key="$(web_react_manifest_key)" > /dev/null 2>&1 || \
		(printf "\e[31m\tFailed to find latest tagged image at '$(descriptive_web_react_gcr_path)'.\e[0m\n" >&2; exit 1)

	@ $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(descriptive_web_admin_gcr_path)" \
	       	manifest_key="$(web_admin_manifest_key)" > /dev/null 2>&1 \
	       	|| $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(web_admin_gcr_path_default_branch)" \
	       	manifest_key="$(web_admin_manifest_key)" > /dev/null 2>&1 || \
		(printf "\e[31m\tFailed to find latest tagged image at '$(descriptive_web_admin_gcr_path)'.\e[0m\n" >&2; exit 1)

	@ $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(descriptive_ingress_gcr_path)" \
	       	manifest_key="$(ingress_manifest_key)" > /dev/null 2>&1 || \
	  $(MAKE) --no-print-directory -f $(this_file) append_to_manifest gcr_path="$(ingress_gcr_path_default_branch)" \
	  manifest_key="$(ingress_manifest_key)" > /dev/null 2>&1 || \
		(printf "\e[31m\tFailed to find latest tagged image at '$(descriptive_ingress_gcr_path)'.\e[0m\n" >&2; exit 1)

.PHONY: append_to_manifest
append_to_manifest: gcr_path :=
append_to_manifest: manifest_key :=
append_to_manifest: # this should only be run by the build server
	@ printf "Looking up '$(gcr_path)'" >&2
	@ export DIGEST="$$(gcloud container images list-tags $(gcr_path) --filter="tags:latest" --format="value(Digest)" || exit 1)" && \
		if [ -n "$$DIGEST" ]; then printf "%s = \"%s@%s\"\n" "$(manifest_key)" "$(gcr_path)" "$$DIGEST" >> $(manifest_file); else exit 1; fi

.PHONY: check_for_abandoned_workspaces
check_for_abandoned_workspaces: ## compare terraform workspaces against git branches to identify potentially-forgotten resources
	$(MAKE) --no-print-directory --silent -f $(this_file) tf_init && \
	$(MAKE) --no-print-directory --silent -f $(this_file) tf_workspace_list | tr -s '\n' | awk '{print $$NF}' | sort > $(vulcan_path)/workspaces
	@ [ -n "$$CI" ] || (git remote update --prune)
	@ git branch --list --remote | awk -F / '{print $$NF}' | sort > $(vulcan_path)/branches
	@ export maybe_orphans="$$(comm -23 $(vulcan_path)/workspaces $(vulcan_path)/branches | grep -v default)"; if [ -n "$$maybe_orphans" ]; then printf "The following workspaces do not have corresponding branches:\n%s\n" "$$maybe_orphans" && exit 1; fi
