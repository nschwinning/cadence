# Cadence backend — FastAPI on uv-managed Python 3.12
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Bring in the uv binary (pinned to match local tooling)
COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest (src, alembic config, migrations) and install the project itself
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Default (prod-ish) command; Compose overrides this to run migrations + --reload
CMD ["uvicorn", "cadence.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
