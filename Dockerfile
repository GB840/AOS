# =============================================================================
# AOS v5.0 Multi-Stage Dockerfile
# =============================================================================

# ---- Stage 1: Builder ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
RUN pip install uv==0.1.18

# Copy dependency files first (for caching)
COPY requirements.txt pyproject.toml ./

# Install dependencies in isolated environment
RUN uv pip install --system --no-cache -r requirements.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim AS production

# Security: create non-root user
RUN groupadd --gid 1000 aos && \
    useradd --uid 1000 --gid aos --shell /bin/bash --create-home aos

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=aos:aos . .

# Create necessary directories with correct permissions
RUN mkdir -p /app/data/sqlite /app/data/chroma /app/outputs /app/logs \
    && chown -R aos:aos /app/data /app/outputs /app/logs

# Switch to non-root user
USER aos

# Expose ports
EXPOSE 8000 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: run API server
# Use docker-compose or make commands to switch between modes
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
