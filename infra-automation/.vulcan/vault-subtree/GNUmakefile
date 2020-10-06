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

uname_s := $(shell uname -s)

vulcan_path := $(dir $(lastword $(MAKEFILE_LIST))).vulcan

vault_version := 1.2.3
vault_path := $(vulcan_path)/$(uname_s)
vault_binary := $(vault_path)/vault
vault_zip := $(vault_path)/vault_$(vault_version)_$(uname_s)_amd64.zip

vault_token_filename := .vault-token
vault_okta_token := $(HOME)/$(vault_token_filename)

vault_address := https://vault-prod.erboh.cloud
vault_tls_skip_verify := false

.PHONY: help
help:
	@ printf "This is meant to be used as a submodule or subtree in other git repos rather than run directly.\n" >&2

.PHONY: vault_version
vault_version: $(vault_binary)
	export PATH="$(vulcan_path)/$(uname_s)" && vault version

.PHONY: vault_login
vault_login:
	@ if [ -n "$$CI" ]; then $(MAKE) --no-print-directory --file $(this_file) vault_approle_login; else $(MAKE) --no-print-directory --file $(this_file) vault_okta_login; fi

.PHONY: vault_okta_login
vault_okta_login: purge_expired_vault_token $(vault_okta_token)
	@:

.PHONY: vault_approle_login
vault_approle_login:
	@ printf "in the future, vault_approle_login will actually do an approle login\n" >&2

.PHONY: get_vault_token_for_ci
get_vault_token_for_ci: ## AppRole login (pass-thru to helper script)
	@ export VAULT_ADDRESS="$(vault_address)"; \
		if [ \( -z "$$VAULT_SECRET_ID" \) -o \( -z "$$VAULT_ROLE_ID" \) ]; then \
		 { printf "%s\n" "You must provide a Vault role and secret id pair via the environment variables 'VAULT_ROLE_ID' and 'VAULT_SECRET_ID'" >&2; exit 1; }; \
		 fi; \
		$(dir $(lastword $(MAKEFILE_LIST)))/helpers/$@.py

.PHONY: purge_expired_vault_token
purge_expired_vault_token:
	@ find $(HOME) -maxdepth 1 -type f -name "$(vault_token_filename)" -mmin +1380 -exec rm {} \;

$(vault_okta_token): $(vault_binary)
	@ export USERNAME="$$(read -p 'enter your okta username: ' -r USERNAME; echo $${USERNAME})"; \
		export PASSWORD="$$(stty -echo; read -p 'enter your okta password: ' -r PASSWORD; stty echo; echo $${PASSWORD})"; \
		(export PATH="$(vulcan_path)/$(uname_s)" && \
			vault login -no-print -address=$(vault_address) -tls-skip-verify=$(vault_tls_skip_verify) -method=okta username=$${USERNAME} password=$${PASSWORD}) || \
			(rm -f $(vault_okta_token); printf "\nvault auth failed!\n" >&2; exit 1)
	@ printf "\nSuccessfully authenticated!\n" >&2

$(vault_binary): $(vault_zip)
	@ if command -p -V unzip; then unzip -o -DD $(vault_zip) -d $(vault_path); \
		else gunzip --stdout <$(vault_zip) > $(vault_binary) && chmod +x $(vault_binary); fi

