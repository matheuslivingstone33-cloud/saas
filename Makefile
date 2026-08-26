# Atalhos de desenvolvimento. Tudo roda SEM CHAVE.
PY := backend/.venv/Scripts/python.exe
ALEMBIC := backend/.venv/Scripts/alembic.exe
RUFF := backend/.venv/Scripts/ruff.exe

.PHONY: help setup migrate seed api worker test lint demo up down logs front-build

help:
	@echo "setup       - cria venv e instala dependencias do backend"
	@echo "migrate     - aplica as migrations (Alembic)"
	@echo "seed        - popula dados de demonstracao"
	@echo "api         - sobe a API em http://localhost:8000"
	@echo "worker      - sobe o worker RQ (exige REDIS_URL)"
	@echo "test        - roda a suite (sem docker, sem rede, sem chave)"
	@echo "lint        - ruff check"
	@echo "demo        - demo da Fase 0 ponta a ponta"
	@echo "smoke P=x   - smoke test de um provedor (Fase 7)"
	@echo "up / down   - docker compose (dev)"
	@echo "prod        - docker compose de producao"

setup:
	cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt

migrate:
	cd backend && ../$(ALEMBIC) upgrade head

seed:
	cd backend && ../$(PY) -m app.db.seed

api:
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8000

worker:
	cd backend && ../$(PY) -m app.workers.worker

test:
	cd backend && ../$(PY) -m pytest -q

lint:
	cd backend && ../$(RUFF) check app tests scripts alembic

demo:
	cd backend && ../$(PY) scripts/demo_fase0.py

front-build:
	cd frontend && npm install && npm run build

smoke:
	cd backend && ../$(PY) scripts/smoke.py $(P)

up:
	docker compose up --build

prod:
	docker compose -f docker-compose.prod.yml up -d --build

down:
	docker compose down

logs:
	docker compose logs -f backend worker
