
help: ## This help menu.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help

# DOCKER TASKS
start: ## Start storage containers (redis and postgres)
	@echo " ============= Running containers ============= "
	docker compose -f ./.devcontainer/docker-compose.yml up -d
