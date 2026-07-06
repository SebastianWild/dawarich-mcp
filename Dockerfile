FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

COPY pyproject.toml uv.lock* ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable || uv sync --no-dev --no-editable

FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

USER 65532:65532

EXPOSE 8000

CMD ["dawarich-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
