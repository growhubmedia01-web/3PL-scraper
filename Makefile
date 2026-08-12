.PHONY: help doctor build-sql install seed seed-local api api-local worker beat frontend test lint clean

help:
	@echo "make doctor     - diagnose setup: db, schema, keys, row counts"
	@echo "make build-sql  - regenerate migrations/ALL_IN_ONE.sql"
	@echo "make install    - install backend + frontend dependencies"
	@echo "make seed       - create schema and seed the 3PL service config"
	@echo "make api        - run the FastAPI server (http://localhost:8000/docs)"
	@echo "make worker     - run the Celery worker"
	@echo "make beat       - run the Celery scheduler"
	@echo "make frontend   - run the React dashboard (http://localhost:5173)"
	@echo "make test       - run the backend test suite"

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

doctor:
	cd backend && python -m scripts.check_setup

build-sql:
	cd backend && python -m scripts.build_all_in_one

seed:
	cd backend && python -m scripts.seed

seed-local:
	cd backend && DATABASE_URL="sqlite+pysqlite:///./local.db" \
		python -m scripts.seed --local

api-local:
	cd backend && DATABASE_URL="sqlite+pysqlite:///./local.db" \
		uvicorn app.main:app --reload --port 8000

seed-sql:
	cd backend && python -m scripts.seed --sql

api:
	cd backend && python run.py

worker:
	cd backend && celery -A app.workers.celery_app worker --loglevel=info

beat:
	cd backend && celery -A app.workers.celery_app beat --loglevel=info

frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest

lint:
	cd backend && python -m compileall -q app
	cd frontend && npm run typecheck

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/local.db frontend/dist
