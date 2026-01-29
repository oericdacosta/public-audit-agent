.PHONY: up down restart logs shell clean lint test typecheck format install check security

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
# Development Commands
# ──────────────────────────────────────────────────────────
install:
	uv sync --dev
	pre-commit install
	@echo "✅ Dev environment ready!"

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/ --ignore-missing-imports

test:
	uv run pytest tests/ -v --cov=src --cov-report=term-missing

test-fast:
	uv run pytest tests/unit/ -v -x

# ──────────────────────────────────────────────────────────
# Security & Quality
# ──────────────────────────────────────────────────────────
security:
	uv run pip-audit --requirement requirements.txt || true

check: lint typecheck test
	@echo "✅ All checks passed!"

# ──────────────────────────────────────────────────────────
# Database Commands
# ──────────────────────────────────────────────────────────
init-db:
	@echo "Initializing database schema..."
	$(COMPOSE) exec $(SERVICE_NAME) python -c \
		"from src.etl.db_manager import DatabaseManager; \
		DatabaseManager().initialize_schema(); \
		print('Database schema initialized!')"

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
	@echo "✅ Cleanup complete!"
