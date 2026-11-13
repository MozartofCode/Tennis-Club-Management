.PHONY: help setup install dev backend frontend check-port test lint seed train build

# The API port is deliberately not 8000, which other local Python apps often hold.
# Override either one: make dev API_PORT=8790 WEB_PORT=5190
API_PORT ?= 8787
WEB_PORT ?= 5173

help:               ## List the commands
	@grep -E '^[a-z-]+:.*##' Makefile | sed 's/:.*## /\t/' | expand -t 20

setup: install seed ## First run: install everything and create the demo club

install:            ## Install backend + frontend dependencies
	cd backend && uv sync
	cd frontend && npm install

check-port:
	@if lsof -iTCP:$(API_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "Port $(API_PORT) is already in use by another program."; \
		echo "Pick a free one, for example: make dev API_PORT=8790"; \
		exit 1; \
	fi

backend: check-port ## Run the API only
	cd backend && uv run uvicorn app.main:app --reload --port $(API_PORT)

frontend:           ## Run the web app only (proxies /api to API_PORT)
	cd frontend && API_PORT=$(API_PORT) npm run dev -- --port $(WEB_PORT)

dev: check-port     ## Run the API and the web app together (Ctrl+C stops both)
	@echo "API on http://localhost:$(API_PORT), web app below (Vite picks the next free port if $(WEB_PORT) is taken)"
	@$(MAKE) -j2 --no-print-directory backend frontend

test:               ## Backend tests
	cd backend && uv run pytest -q

lint:               ## Lint and format checks
	cd backend && uv run ruff check app tests scripts && uv run ruff format --check app tests scripts
	cd frontend && npm run lint

seed:               ## Reset the local database and create the demo club
	cd backend && uv run python -m scripts.seed

train:              ## Model accuracy and the pricing simulation for the local database
	cd backend && uv run python -m scripts.train

build:              ## Production build of the frontend
	cd frontend && npm run build
