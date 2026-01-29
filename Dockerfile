FROM python:3.12-slim

# Install UV (The Modern Python Package Manager) - Pinned version for stability
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv

WORKDIR /app

# Install system dependencies
# gcc is needed for some python extensions compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy project definition and lockfile first (better layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies using modern uv sync (creates .venv automatically)
RUN uv sync --frozen --no-dev

# Copy source code and config
COPY src/ src/
COPY data/ data/
COPY config.yaml .

# Create directories for logs and evals, and set ownership
# We also need to ensure data directory is writable if using SQLite in it
RUN mkdir -p logs evals data && \
    chown -R appuser:appuser /app

# Switch to non-root user for security
USER appuser

# Expose TCP port
EXPOSE 8000

# Set Python path to include root
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command runs the MCP server with TCP transport using uv run
CMD ["uv", "run", "python", "src/mcp/server.py", "--transport", "tcp", "--port", "8000"]
