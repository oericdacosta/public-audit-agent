# ============================================================
# Builder
# ============================================================
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv

WORKDIR /app

# Instalar dependências de compilação (apenas no builder)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar apenas arquivos de dependência (melhor cache de camadas)
COPY pyproject.toml uv.lock ./

# Instalar dependências em .venv isolado
RUN uv sync --frozen --no-dev

# ============================================================
# Runtime
# ============================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv

COPY --from=builder /app/.venv /app/.venv

COPY src/ src/
COPY dbt/ dbt/
COPY config.yaml .

RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && mkdir -p logs data evals \
    && chown -R appuser:appuser /app


USER appuser

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.connect(('localhost', 8000)); s.close()" || exit 1

CMD ["python", "-m", "src.mcp.tcp_server", "--port", "8000"]
