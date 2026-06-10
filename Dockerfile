#
# --- Stage 1: Builder ---
# Installs dependencies into a project-local virtual environment using uv
#
FROM python:3.14-slim AS builder

# --- Install system build dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv (single binary, very fast)
RUN pip install --no-cache-dir uv

# Tell uv to create the virtual environment in the project directory
ENV UV_PROJECT_ENVIRONMENT=.venv

# Copy only dependency files to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Create venv and install production dependencies only
# --frozen ensures uv.lock is respected (CI-safe)
# --no-dev excludes development dependencies
# --no-install-project mirrors Poetry's --no-root
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the application source code
COPY . .


#
# --- Stage 2: Final Image ---
# Small production runtime image
#
FROM python:3.14-slim AS final

WORKDIR /app

# Create non-root user
RUN addgroup --system nonroot && adduser --system --ingroup nonroot nonroot

# Copy virtual environment
COPY --from=builder /app/.venv ./.venv

# Copy application source
COPY --from=builder /app .

# Make startup script executable
RUN chmod +x ./scripts/startup.sh

# Activate virtualenv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Set ownership
RUN chown -R nonroot:nonroot /app

USER nonroot

CMD ["./scripts/startup.sh"]
