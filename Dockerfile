FROM python:3.11-slim

# Install UV (The Modern Python Package Manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install system dependencies
# gcc is still needed for some python extensions compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements or pyproject.toml
# Since we have requirements.txt frozen by uv, we use it directly for stability
COPY requirements.txt .

# Install dependencies using UV (Much faster than pip)
RUN uv pip install --system --no-cache -r requirements.txt

# Copy source code
COPY src/ src/
COPY data/ data/
RUN mkdir -p logs evals

# Expose TCP port
EXPOSE 8000

# Set Python path to include root
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command runs the MCP server with TCP transport
CMD ["python", "src/mcp/server.py", "--transport", "tcp", "--port", "8000"]
