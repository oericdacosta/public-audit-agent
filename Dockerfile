FROM python:3.11-slim

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

# Copy requirements
COPY requirements.txt .

# Install dependencies using UV (System-wide is fine as we are in a container)
RUN uv pip install --system --no-cache -r requirements.txt

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

# Default command runs the MCP server with TCP transport
CMD ["python", "src/mcp/server.py", "--transport", "tcp", "--port", "8000"]
