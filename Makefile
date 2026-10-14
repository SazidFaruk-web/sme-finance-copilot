# Convenience targets (Linux/macOS/WSL). On Windows without make, run the python commands directly.
PY ?= python

.PHONY: install test cov demo serve seed bench evidence verify finetune docker-up docker-local

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

docker-local:    ## app + Ollama with a local 7B model; nothing leaves the machine
	docker compose --profile local-llm up --build
