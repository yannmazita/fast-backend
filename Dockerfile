#
# --- Stage 1: Builder ---
# This stage installs dependencies into a virtual environment.
#
FROM python:3.13-slim AS builder

# --- Install system build dependencies ---
# This is necessary for packages that compile C extensions (like  bcrypt, argon2-cffi).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Install Poetry
RUN pip install poetry==2.1.3

# Tell Poetry to create the virtual environment in the project's root directory
RUN poetry config virtualenvs.in-project true

# Copy only the dependency files to leverage Docker cache
COPY pyproject.toml poetry.lock ./

# Install production dependencies.
# --no-interaction and --no-ansi are recommended for CI/CD environments.
# --without dev ensures development dependencies are not installed.
# -v flag is added for verbose output to help diagnose issues.
RUN poetry install --no-interaction --no-ansi --without dev --no-root -v

# Copy the rest of the application source code
COPY . .


#
# --- Stage 2: Final Image ---
# This stage creates the small, secure final image for production.
#
FROM python:3.13-slim AS final

WORKDIR /app

# Create a non-root user to run the application
RUN addgroup --system nonroot && adduser --system --ingroup nonroot nonroot

# Copy the virtual environment with installed dependencies from the builder stage
COPY --from=builder /app/.venv ./.venv

# Copy the application code and necessary files from the builder stage
#COPY --from=builder /app/scripts/startup.sh ./scripts/startup.sh
#COPY --from=builder /app/src ./src
#COPY --from=builder /app/alembic ./alembic
#COPY --from=builder /app/alembic.ini ./alembic.ini

# Or
# Copy the entire application source code from the builder stage.
COPY --from=builder /app .

# Make the startup script executable
RUN chmod +x ./scripts/startup.sh

# Add the virtual environment's bin directory to the PATH.
ENV PATH="/app/.venv/bin:$PATH"

# Change ownership of the app directory to the non-root user
RUN chown -R nonroot:nonroot /app

# Add the application's root directory to the PYTHONPATH.
ENV PYTHONPATH="/app"

# Switch to the non-root user
USER nonroot

# Run the startup script from its new location
CMD ["./scripts/startup.sh"]
