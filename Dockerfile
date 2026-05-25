FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Install Playwright browser dependencies and Chromium
RUN uv run playwright install-deps chromium && \
    uv run playwright install chromium

COPY backend/ ./backend/

EXPOSE 8000
CMD ["uv", "run", "granian", "--interface", "asgi", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--access-log"]
