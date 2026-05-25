LLAMA_HOST ?= 127.0.0.1
LLAMA_PORT ?= 8000
LLAMA_BASE_URL ?= http://$(LLAMA_HOST):$(LLAMA_PORT)
LLAMA_STARTUP_TIMEOUT_SECONDS ?= 120
BREW_BIN ?= /opt/homebrew/bin/brew
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8001
BACKEND_BASE_URL ?= http://$(BACKEND_HOST):$(BACKEND_PORT)

# llama-server model & hyperparameters configurations
VIVA_LLM_MODEL ?= models/gemma-4-E4B-it-Q4_K_M.gguf
VIVA_LLM_MMPROJ ?= models/mmproj-F16.gguf
VIVA_LLM_CTX_SIZE ?= 32768
VIVA_LLM_N_GPU_LAYERS ?= -1
VIVA_LLM_TEMP ?= 0.3
VIVA_LLM_TOP_P ?= 0.9
VIVA_LLM_TOP_K ?= 40

.PHONY: help
help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: lint
lint: ## lint code
	uv run ruff format src
	uv run ruff check --fix src

.PHONY: ensure-llama
ensure-llama: ## ensure the llama-server is running
	@mkdir -p .logs
	@if curl -fsS "$(LLAMA_BASE_URL)/v1/models" >/dev/null 2>&1; then \
		echo "llama-server already running at $(LLAMA_BASE_URL)."; \
	else \
		echo "Starting llama-server in the background..."; \
		if [ ! -f "$(VIVA_LLM_MODEL)" ]; then \
			echo "Warning: LLM model file '$(VIVA_LLM_MODEL)' not found."; \
			echo "Please ensure the model file is located at '$(VIVA_LLM_MODEL)' or configure VIVA_LLM_MODEL."; \
		fi; \
		mmproj_flag=""; \
		if [ -f "$(VIVA_LLM_MMPROJ)" ]; then \
			mmproj_flag="--mmproj $(VIVA_LLM_MMPROJ)"; \
		else \
			echo "Note: MMPROJ model file '$(VIVA_LLM_MMPROJ)' not found. Vision support will be disabled."; \
		fi; \
		llama_bin="llama-server"; \
		if ! command -v "$$llama_bin" >/dev/null 2>&1; then \
			brew_bin="$(BREW_BIN)"; \
			if [ ! -x "$$brew_bin" ]; then \
				brew_bin="$$(command -v brew 2>/dev/null || true)"; \
			fi; \
			if [ -n "$$brew_bin" ] && [ -x "$$brew_bin" ]; then \
				echo "llama-server not found in PATH. Attempting to install via Homebrew..."; \
				"$$brew_bin" install llama.cpp; \
			else \
				echo "Error: llama-server not found and Homebrew is not available."; \
				echo "Please install llama.cpp and ensure llama-server is in your PATH."; \
				exit 1; \
			fi; \
		fi; \
		nohup llama-server \
			--model "$(VIVA_LLM_MODEL)" \
			$$mmproj_flag \
			--port "$(LLAMA_PORT)" \
			--ctx-size "$(VIVA_LLM_CTX_SIZE)" \
			--n-gpu-layers "$(VIVA_LLM_N_GPU_LAYERS)" \
			--flash-attn on \
			--temp "$(VIVA_LLM_TEMP)" \
			--top-p "$(VIVA_LLM_TOP_P)" \
			--top-k "$(VIVA_LLM_TOP_K)" \
			> .logs/llama-server.log 2>&1 & \
		attempt=1; \
		while [ "$$attempt" -le "$(LLAMA_STARTUP_TIMEOUT_SECONDS)" ]; do \
			if curl -fsS "$(LLAMA_BASE_URL)/v1/models" >/dev/null 2>&1; then \
				echo "llama-server is ready."; \
				break; \
			fi; \
			if [ "$$attempt" = "$(LLAMA_STARTUP_TIMEOUT_SECONDS)" ]; then \
				echo "llama-server did not become ready. Check .logs/llama-server.log"; \
				exit 1; \
			fi; \
			attempt=$$((attempt + 1)); \
			sleep 1; \
		done; \
	fi

.PHONY: backend
backend: ensure-llama ## ensure llama-server is running, then launch the backend
	@if curl -fsS "$(BACKEND_BASE_URL)/health" >/dev/null 2>&1; then \
		echo "Viva backend already running at $(BACKEND_BASE_URL)."; \
		exit 0; \
	fi
	@exec env VIVA_LLM_MODEL="$(VIVA_LLM_MODEL)" VIVA_LLM_BASE_URL="$(LLAMA_BASE_URL)/v1" VIVA_OMLX_MODEL="$(VIVA_LLM_MODEL)" VIVA_OMLX_BASE_URL="$(LLAMA_BASE_URL)/v1" VIVA_BACKEND_HOST="$(BACKEND_HOST)" VIVA_BACKEND_PORT="$(BACKEND_PORT)" uv run python src/viva_api_server.py
