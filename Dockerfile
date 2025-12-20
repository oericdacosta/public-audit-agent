FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (gcc for potential python build deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ src/
COPY data/ data/
# Create empty dirs for logs and evals if they don't exist
RUN mkdir -p logs evals

# Expose TCP port
EXPOSE 8000

# Set Python path to include root
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command runs the MCP server with TCP transport
CMD ["python", "src/mcp/server.py", "--transport", "tcp", "--port", "8000"]
