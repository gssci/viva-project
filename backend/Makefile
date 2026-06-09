BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8001
BACKEND_BASE_URL ?= http://$(BACKEND_HOST):$(BACKEND_PORT)
VIVA_LLM_MODEL ?= google/google/gemma-4-e4b
VIVA_LLM_BASE_URL ?= http://127.0.0.1:1234/v1
VIVA_LLM_API_KEY ?= lm-studio

.PHONY: help
help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: lint
lint: ## lint code
	uv run ruff format src
	uv run ruff check --fix src

.PHONY: backend
backend: ## launch the backend
	@if curl -fsS "$(BACKEND_BASE_URL)/health" >/dev/null 2>&1; then \
		echo "Viva backend already running at $(BACKEND_BASE_URL)."; \
		exit 0; \
	fi
	@exec env VIVA_LLM_MODEL="$(VIVA_LLM_MODEL)" VIVA_LLM_BASE_URL="$(VIVA_LLM_BASE_URL)" VIVA_LLM_API_KEY="$(VIVA_LLM_API_KEY)" VIVA_BACKEND_HOST="$(BACKEND_HOST)" VIVA_BACKEND_PORT="$(BACKEND_PORT)" uv run python src/viva_api_server.py
