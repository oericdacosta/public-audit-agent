.PHONY: up down restart logs shell clean lint test typecheck format install check security docker-build docker-test ci

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
# Development Commands
# ──────────────────────────────────────────────────────────
install:
	uv sync --dev
	pre-commit install
	@echo "✅ Dev environment ready!"

lint:
	@echo "🔍 Running Linter..."
	uv run ruff check src/ tests/

format:
	@echo "🎨 Checking Format..."
	uv run ruff format --check src/ tests/

fix:
	@echo "🛠️  Fixing Lint and Format..."
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/
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
	@uv run python -m src.etl.main --municipality 162
	@echo "✅ ETL complete!"

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
