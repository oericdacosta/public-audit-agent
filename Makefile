.PHONY: setup etl clean

# Default variables (can be overridden: make etl MUNICIPALITY=162 YEAR=2024)
MUNICIPALITY ?= 162
YEAR ?= 2024

setup:
	@echo "Creating virtual environment and installing dependencies..."
	uv venv
	uv pip install -r requirements.txt

etl:
	@echo "Running ETL for Municipality $(MUNICIPALITY) - Year $(YEAR)..."
	.venv/bin/python -m src.etl.main --municipality $(MUNICIPALITY) --year $(YEAR)

clean:
	@echo "Cleaning temporary files..."
	rm -rf __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -delete
