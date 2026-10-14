# Convenience targets (Linux/macOS/WSL). On Windows without make, run the python commands directly.
PY ?= python

LLAMA_SERVER ?= llama-server
LLM_MODEL ?= models/Qwen3.5-9B-Q5_K_M.gguf

.PHONY: install test cov demo serve seed bench evidence verify finetune docker-up docker-local local-llm

install:
	$(PY) -m pip install -r requirements-dev.txt

test:
	$(PY) -m pytest

cov:
	$(PY) -m pytest --cov=sme_copilot --cov-report=term-missing --cov-report=html

demo:            ## reset + seed demo persona + serve on :8000 (offline, no API keys)
	APP_ENV=demo $(PY) -m sme_copilot.cli demo

serve:
	$(PY) -m sme_copilot.cli serve

seed:
	$(PY) -m sme_copilot.cli seed --reset

bench:           ## e.g. make bench PROFILES=rules-offline,claude-sonnet,local-qwen7b
	$(PY) -m sme_copilot.cli bench --profiles $(or $(PROFILES),rules-offline)

evidence:
	$(PY) -m sme_copilot.cli evidence

verify:
	$(PY) -m sme_copilot.cli verify-audit

finetune:
	$(PY) -m sme_copilot.cli export-finetune --include-unrated

docker-up:
	docker compose up --build

local-llm:       ## llama.cpp server for the local-llamacpp profile (Windows: scripts\start_local_llm.bat)
	$(LLAMA_SERVER) -m $(LLM_MODEL) --host 127.0.0.1 --port 8080 -ngl 99 -c 16384 -fa off --reasoning off -cram 2048

docker-local:    ## app + Ollama with a local 7B model; nothing leaves the machine
	docker compose --profile local-llm up --build
