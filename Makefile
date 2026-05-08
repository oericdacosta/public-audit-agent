.PHONY: up down restart logs shell clean lint test typecheck format install check security docker-build docker-test ci airflow-up airflow-down airflow-logs airflow-restart airflow-trigger agent-up mcp-up mcp-down

# Project Variables
COMPOSE = docker compose
SERVICE_NAME = app

# ──────────────────────────────────────────────────────────
# Docker Commands
# ──────────────────────────────────────────────────────────
up:
	@echo "Starting Docker environment..."
	$(COMPOSE) up -d --build
	@echo "Environment running. Use 'make logs' to see output."

down:
	@echo "Stopping Docker environment..."
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f $(SERVICE_NAME)

shell:
	$(COMPOSE) exec $(SERVICE_NAME) bash

# ──────────────────────────────────────────────────────────
# Docker Build (Local)
# ──────────────────────────────────────────────────────────
docker-build:
	@echo "Building Docker image..."
	docker buildx build --load -t public-audit-agent:local .
	@echo "✅ Image built: public-audit-agent:local"

docker-test: docker-build
	@echo "Testing Docker image..."
	docker run --rm public-audit-agent:local python -c "from src.config import get_settings; print('✅ Config OK')"
	@echo "✅ Docker image test passed!"

# ──────────────────────────────────────────────────────────
# Agent / Chat Commands
# ──────────────────────────────────────────────────────────
MCP_PID_FILE := .mcp_server.pid

mcp-up:
	@echo "🔌 Starting MCP TCP server (0.0.0.0:8000)..."
	@fuser -k 8000/tcp 2>/dev/null || true
	@sleep 0.5
	@uv run python -m src.mcp.tcp_server --host 0.0.0.0 & echo $$! > $(MCP_PID_FILE)
	@sleep 1
	@echo "✅ MCP server running (PID=$$(cat $(MCP_PID_FILE)))"

mcp-down:
	@if [ -f $(MCP_PID_FILE) ]; then \
		kill $$(cat $(MCP_PID_FILE)) 2>/dev/null && echo "🛑 MCP server stopped" || echo "⚠️  MCP server already stopped"; \
		rm -f $(MCP_PID_FILE); \
	else \
		echo "⚠️  No MCP PID file found"; \
	fi

agent-up: mcp-up
	@echo "🌐 Ensuring Docker network exists..."
	@docker network inspect public-audit-agent_net >/dev/null 2>&1 \
		|| docker network create public-audit-agent_net
	@echo "💬 Starting chat interface... (Ctrl+C to quit)"
	@MCP_HOST=host.docker.internal uv run python scripts/chat.py; $(MAKE) mcp-down

# ──────────────────────────────────────────────────────────
# Development Commands
# ──────────────────────────────────────────────────────────
install:
	uv sync --dev
	pre-commit install
	@echo "✅ Dev environment ready!"

lint:
	@echo "🔍 Running Linter..."
	uv run ruff check src/ tests/
	uv run sqlfluff lint dbt/models/

format:
	@echo "🎨 Checking Format..."
	uv run ruff format --check src/ tests/

fix:
	@echo "🛠️  Fixing Lint and Format..."
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/
	uv run sqlfluff fix dbt/models/
	@echo "✅ Code fixed!"

typecheck:
	@echo "🔷 Running Type Checker..."
	uv run mypy src/ --ignore-missing-imports

test:
	@echo "🧪 Running Tests..."
	uv run pytest tests/ -v --cov=src --cov-report=term-missing

test-fast:
	uv run pytest tests/unit/ -v -x

# ──────────────────────────────────────────────────────────
# Security & Quality
# ──────────────────────────────────────────────────────────
security:
	@echo "Running security scans..."
	uv export --no-dev > requirements.txt
	uv run pip-audit --requirement requirements.txt
	uv run bandit -r src/ -ll -ii
	rm requirements.txt
	@echo "✅ Security scan complete!"

check: lint format typecheck test
	@echo "✅ All checks passed!"

ci: check security
	@echo "✅ CI simulation complete!"

# ──────────────────────────────────────────────────────────
# Database Commands
# ──────────────────────────────────────────────────────────
init-db:
	@echo "Initializing database schema..."
	$(COMPOSE) exec $(SERVICE_NAME) python -c \
		"from src.etl.db_manager import DatabaseManager; \
		DatabaseManager().initialize_schema(); \
		print('Database schema initialized!')"

etl:
	@echo "Running ETL process..."
	@uv run python -m src.etl.main --municipality $(or $(municipality),162) $(if $(year),--year $(year),)
	@echo "✅ ETL complete!"

# ──────────────────────────────────────────────────────────
# Airflow Commands
# ──────────────────────────────────────────────────────────
airflow-up:
	@echo "🚀 Starting Airflow..."
	@mkdir -p logs/airflow data
	@grep -q '^AIRFLOW_UID=' .env 2>/dev/null || echo "AIRFLOW_UID=$$(id -u)" >> .env
	docker compose -f docker-compose.airflow.yml up -d
	@echo "✅ Airflow running at http://localhost:8080 (admin/admin)"

airflow-down:
	@echo "Stopping Airflow..."
	docker compose -f docker-compose.airflow.yml down

airflow-logs:
	docker compose -f docker-compose.airflow.yml logs -f airflow-scheduler

airflow-restart: airflow-down airflow-up

airflow-trigger:
	@echo "🔄 Triggering ETL DAG..."
	docker compose -f docker-compose.airflow.yml exec airflow-webserver \
		airflow dags trigger civic_audit_etl

# ──────────────────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────────────────
clean: down
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type f -name "coverage.xml" -delete 2>/dev/null || true
	rm -rf dbt/target dbt/dbt_packages dbt/logs
	uv run pre-commit clean
	@echo "✅ Cleanup complete!"
