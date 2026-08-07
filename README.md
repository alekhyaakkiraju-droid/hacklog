==================
What is Hacklog?
==================

Hacklog is a security software that detects compromised user accounts 
by applying statistical analysis to service access logs.

Hacklog is implemented as a system daemon that accepts a log stream via the
syslog protocol (UDP, default port 10514).


http://dandb.github.io/hacklog/

Development
============

[![CI](https://github.com/alekhyaakkiraju-droid/hacklog/actions/workflows/ci.yml/badge.svg)](https://github.com/alekhyaakkiraju-droid/hacklog/actions/workflows/ci.yml)

Clone repository and install the project
```
git clone git@github.com:alekhyaakkiraju-droid/hacklog.git
cd hacklog
pip install -e ".[test,dev]"
pytest tests/
```

### Branch protection

Configure the following rules on `main` / `master` / `release-next` in GitHub repository settings (**Settings → Branches → Add rule**):

- Require a pull request before merging
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Required status check: **CI / quality (3.12)** and **CI / quality (3.13)**

This ensures ruff, black, isort, mypy, bandit, and pytest all pass before merge.

Start software (development, without Docker)
```
cd hacklog/hacklog
./run.sh    # start service
./stop.sh   # stop  service
```

Deployment — Docker (recommended)
===================================

### Quick start

1. Copy the example environment file and fill in the required SMTP secrets:

```bash
cp .env.example .env
$EDITOR .env   # set HACKLOG_SMTP_USER, HACKLOG_SMTP_PASSWORD, etc.
```

2. Build and start the container:

```bash
# Build the image
docker build -t hacklog:latest .

# Run the container (reads secrets from .env)
docker run -d \
  --name hacklog \
  --env-file .env \
  -e HACKLOG_SYSLOG_BIND_ADDRESS=0.0.0.0 \
  -e HACKLOG_DATABASE_DB_URL=sqlite:////data/hacklog.db \
  -p 10514:10514/udp \
  -v hacklog_data:/data \
  -v hacklog_logs:/var/log/hacklog \
  hacklog:latest
```

3. Verify the container is healthy:

```bash
docker ps                         # check STATUS = healthy
docker logs hacklog               # inspect startup output
```

4. Send a test syslog message:

```bash
echo "<1>Jan  1 00:00:00 testhost sshd[1234]: Accepted password for alice from 10.0.0.1 port 22 ssh2" \
  | nc -u -w1 127.0.0.1 10514
```

### docker-compose (dev/test)

```bash
cp .env.example .env && $EDITOR .env   # fill in SMTP secrets
docker compose up -d                   # start hacklog
docker compose ps                      # confirm healthy
```

Start with optional Prometheus monitoring:

```bash
docker compose --profile monitoring up -d
# Prometheus UI: http://localhost:9091
```

### Environment variables

All hacklog configuration is supplied via environment variables.  No secrets
must ever appear in the Dockerfile or docker-compose.yml.

| Variable | Required | Default | Description |
|---|---|---|---|
| `HACKLOG_SMTP_HOST` | Yes | `smtp.gmail.com` | SMTP server hostname |
| `HACKLOG_SMTP_PORT` | No | `587` | SMTP server port |
| `HACKLOG_SMTP_USER` | Yes | — | SMTP authentication username |
| `HACKLOG_SMTP_PASSWORD` | Yes | — | SMTP authentication password |
| `HACKLOG_SMTP_SENDER` | Yes | — | From address for alert emails |
| `HACKLOG_ALERT_RECIPIENT` | Yes | — | Destination address for alerts |
| `HACKLOG_SYSLOG_BIND_ADDRESS` | No | `0.0.0.0` | UDP listener bind address |
| `HACKLOG_SYSLOG_PORT` | No | `10514` | UDP listener port |
| `HACKLOG_ALLOWED_CIDRS` | No | *(allow all)* | Comma-separated CIDR allowlist |
| `HACKLOG_DATABASE_DB_URL` | No | `sqlite:////data/hacklog.db` | SQLAlchemy database URL |
| `HACKLOG_METRICS_ENABLED` | No | `false` | Expose Prometheus `/metrics` |
| `HACKLOG_METRICS_PORT` | No | `9090` | Prometheus metrics HTTP port |

See `.env.example` for a complete list including optional scoring overrides.

### Image details

* Base image: `python:3.12-slim` (multi-stage build — only runtime deps shipped)
* Runs as non-root user `hacklog` (UID 1000)
* Health check: verifies UDP port 10514 is bound (30 s interval, 30 s start period)
* Volumes: `/data` (SQLite DB), `/var/log/hacklog` (dead-letter files)
* Exposed port: `10514/udp`

Deployment — systemd
======================

A `hacklog.service` systemd unit is provided for bare-metal / VM deployments.
See `conf/hacklog` for the unit file.

Community
=========

Mailing list

https://groups.google.com/forum/#!forum/hacklog-devel

https://groups.google.com/forum/#!forum/hacklog-users

Chat 
[![Gitter](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/dandb/hacklog?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
