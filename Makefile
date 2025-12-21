.PHONY: up down restart logs verify shell clean

# Project Variables
COMPOSE = docker compose
SERVICE_NAME = app

# Start the environment (builds if necessary)
up:
	@echo "Starting Docker environment..."
	$(COMPOSE) up -d --build
	@echo "Environment running. Use 'make logs' to see output."

# Stop the environment
down:
	@echo "Stopping Docker environment..."
	$(COMPOSE) down

# Restart the environment
restart: down up

# View logs
logs:
	$(COMPOSE) logs -f $(SERVICE_NAME)

# Run the verification script inside the container
verify:
	@echo "Running verification script..."
	$(COMPOSE) exec $(SERVICE_NAME) python src/execution/verify_langgraph.py

# Initialize the database schema (Creates tables with metadata)
init-db:
	@echo "Initializing database schema..."
	$(COMPOSE) exec $(SERVICE_NAME) python -c "from src.etl.database import DatabaseManager; DatabaseManager().initialize_schema(); print('Database schema initialized!')"

# Open a shell inside the container
shell:
	$(COMPOSE) exec $(SERVICE_NAME) bash

# Clean up temporary files and stop containers
clean: down
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
