# ─── Stage 1: builder ────────────────────────────────────────────────────────
# Install runtime dependencies and build the hacklog wheel.
FROM python:3.12-slim AS builder

# Avoid .pyc bytecode in the build layer and unbuffer output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Copy metadata files first for better layer caching.
# hatchling (the build backend) reads README.md and LICENSE when building the wheel.
COPY pyproject.toml README.md LICENSE ./

# Copy application source.  Changing only source invalidates this layer onward
# but preserves the metadata layer above.
COPY hacklog/ ./hacklog/

RUN pip install --no-cache-dir .


# ─── Stage 2: runtime ─────────────────────────────────────────────────────────
# Minimal image containing only the installed package and application source.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create a dedicated non-root system user (UID 1000) for security.
RUN useradd -r -u 1000 -m -s /sbin/nologin hacklog

WORKDIR /app

# Copy installed Python packages from the builder stage.
COPY --from=builder /usr/local/lib/python3.12/site-packages \
                    /usr/local/lib/python3.12/site-packages

# Copy application source so the server can be launched as a script.
# Running `python hacklog/server.py` adds hacklog/ to sys.path[0], which
# satisfies the bare imports (e.g. `from alerting import AlertService`) used
# throughout the package without requiring a PYTHONPATH override.
COPY --from=builder /build/hacklog ./hacklog/

# Copy the health check script used by the HEALTHCHECK instruction.
COPY healthcheck.py /usr/local/bin/healthcheck.py

# Create volume mount points and set ownership before dropping to non-root.
RUN mkdir -p /data /var/log/hacklog \
 && chown -R hacklog:hacklog /data /var/log/hacklog /app

# ── Default environment variables ────────────────────────────────────────────
# Bind to all interfaces so the UDP port is reachable from the Docker host.
ENV HACKLOG_SYSLOG_BIND_ADDRESS=0.0.0.0
# Use the mounted /data volume for the SQLite database.
ENV HACKLOG_DATABASE_DB_URL=sqlite:////data/hacklog.db

# ── Port and volumes ─────────────────────────────────────────────────────────
# Expose the syslog UDP listener port.
EXPOSE 10514/udp

# /data        → SQLite database file (hacklog.db)
# /var/log/hacklog → dead-letter JSON-lines files written on DB failure
VOLUME ["/data", "/var/log/hacklog"]

# Drop privileges to the non-root hacklog user.
USER hacklog

# ── Health check ─────────────────────────────────────────────────────────────
# Verifies the application is running by confirming that UDP port 10514 is
# already bound (i.e. the syslog listener is active).  Exit 0 = healthy.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python /usr/local/bin/healthcheck.py

# ── Entrypoint ───────────────────────────────────────────────────────────────
# Run the syslog server.  Required secrets (HACKLOG_SMTP_USER, etc.) must be
# supplied at container launch via -e / --env-file / docker-compose env section.
CMD ["python", "hacklog/server.py"]
