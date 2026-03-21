FROM python:3.12-slim AS base

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies (with server extra)
RUN uv pip install --system --no-cache ".[server]"

# Copy source code
COPY src/ src/

# Install the package itself
RUN uv pip install --system --no-cache --no-deps .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

ENTRYPOINT ["mergeguard"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
