.PHONY: install dev backend frontend test lint seed train build

install:            ## Install backend + frontend dependencies
	cd backend && uv sync
	cd frontend && npm install

backend:            ## Run the API on :8000
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:           ## Run the web app on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

dev:                ## Run both (Ctrl+C stops both)
	$(MAKE) -j2 backend frontend

test:               ## Backend tests
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check app tests scripts && uv run ruff format --check app tests scripts
	cd frontend && npm run lint

seed:               ## Reset the local database and create the demo club
	cd backend && uv run python -m scripts.seed

train:              ## Print model accuracy and the pricing simulation for the local database
	cd backend && uv run python -m scripts.train

build:              ## Production build of the frontend
	cd frontend && npm run build
