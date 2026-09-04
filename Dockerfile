# Use the official Python image from the Docker Hub
# Stage 1: Build the React/TypeScript dashboard
FROM node:20-slim AS dashboard-builder
WORKDIR /app/dashboard
COPY dashboard/package*.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Install all locales supported by _REGION_PROFILES so any REGION= value works
# at runtime without requiring a rebuild.
RUN apt-get update && apt-get install -y --no-install-recommends locales \
    && printf '%s\n' \
        "en_US.UTF-8 UTF-8" \
        "en_CA.UTF-8 UTF-8" \
        "en_GB.UTF-8 UTF-8" \
        "en_AU.UTF-8 UTF-8" \
        "es_MX.UTF-8 UTF-8" \
        "es_ES.UTF-8 UTF-8" \
        "es_AR.UTF-8 UTF-8" \
        "pt_BR.UTF-8 UTF-8" \
        "pt_PT.UTF-8 UTF-8" \
        "de_DE.UTF-8 UTF-8" \
        "fr_FR.UTF-8 UTF-8" \
        "it_IT.UTF-8 UTF-8" \
        "pl_PL.UTF-8 UTF-8" \
        "ru_RU.UTF-8 UTF-8" \
        "tr_TR.UTF-8 UTF-8" \
        "nl_NL.UTF-8 UTF-8" \
        "ja_JP.UTF-8 UTF-8" \
        "ko_KR.UTF-8 UTF-8" \
        "zh_CN.UTF-8 UTF-8" \
        > /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 appuser \
    && useradd --system --no-create-home --shell /bin/false --uid 1000 --gid 1000 appuser

# Default system locale for the container; the app's date-formatting locale is
# set at runtime via the LOCALE env var (derived from REGION in config.py).
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Copy the pre-built dashboard static files from the builder stage
COPY --from=dashboard-builder /app/dashboard/dist ./dashboard/dist

# Create writable directories for appuser and make healthcheck executable.
# NOTE: /mnt/logs is bind-mounted at runtime only when LOG_TO_FILE=true (see compose.yaml).
# Ensure the host source directory is owned by the UID/GID of appuser in the container.
RUN mkdir -p /mnt/logs \
    && chown appuser:appuser /mnt/logs \
    && chmod +x /app/healthcheck.sh

# Switch to non-root user for all subsequent instructions and runtime
USER appuser

# Expose the REST API port (default 8000, configurable via API_PORT env var)
EXPOSE 8000

# Health check: confirm the main Python process is running
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD /app/healthcheck.sh

# Run the application
CMD ["python", "main.py"]