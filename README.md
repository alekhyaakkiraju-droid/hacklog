# Hacklog

[![CI](https://github.com/alekhyaakkiraju-droid/hacklog/actions/workflows/ci.yml/badge.svg)](https://github.com/alekhyaakkiraju-droid/hacklog/actions/workflows/ci.yml)

Hacklog is a security daemon that detects compromised user accounts by applying statistical analysis to SSH authentication logs. It listens for syslog messages over UDP, scores each authentication event using a weighted surprisal model, and sends email alerts when a user's behaviour deviates significantly from their historical baseline.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Quick Start — Docker](#quick-start--docker)
3. [Quick Start — Bare Metal](#quick-start--bare-metal)
4. [Configuration Reference](#configuration-reference)
5. [Scoring Algorithm](#scoring-algorithm)
6. [Development](#development)
7. [License](#license)

---

## Architecture Overview

Hacklog is structured in six layers:

```
┌─────────────────────────────────────────────────────┐
│  1. Syslog Ingestion  (hacklog/syslog_server.py)     │
│     UDP listener → validates source CIDR →           │
│     rate-limits per source IP                        │
├─────────────────────────────────────────────────────┤
│  2. Parsing           (hacklog/parse.py)             │
│     Extracts username, IP, server, success/fail      │
│     from sshd log lines → EventLog entity            │
├─────────────────────────────────────────────────────┤
│  3. Scoring Engine    (hacklog/scoring.py)           │
│     Weighted surprisal across 6 dimensions →         │
│     compares event to user's profile baseline        │
├─────────────────────────────────────────────────────┤
│  4. Alerting          (hacklog/alerting.py)          │
│     Async SMTP delivery with circuit breaker,        │
│     retry, and dead-letter queue                     │
├─────────────────────────────────────────────────────┤
│  5. Persistence       (hacklog/repositories.py)      │
│     SQLAlchemy ORM → SQLite; repository pattern;     │
│     Alembic migrations; append-only audit trail      │
├─────────────────────────────────────────────────────┤
│  6. Config & Observability                           │
│     pydantic-settings env vars; structlog JSON;      │
│     Prometheus metrics; data retention / purge       │
└─────────────────────────────────────────────────────┘
```

**Key components:**

| Module | Responsibility |
|--------|----------------|
| `syslog_server.py` | Async UDP syslog receiver with CIDR filtering and rate limiting |
| `parse.py` | Converts raw syslog lines into `EventLog` entities |
| `scoring.py` | `ScoringEngine` — computes risk scores and triggers alerts |
| `alerting.py` | `AlertService` — async SMTP with circuit breaker and dead-letter queue |
| `repositories.py` | `UserRepository`, `ProfileRepository`, `AuditRepository` |
| `services.py` | `UpdateService` — profile frequency tracking |
| `retention.py` | `DataRetentionService` — configurable purge with asyncio scheduling |
| `config.py` | `ConfigManager` — pydantic-settings with YAML and env-var support |

---

## Quick Start — Docker

### Prerequisites

- Docker 24+ and Docker Compose v2

### 1. Clone and configure

```bash
git clone https://github.com/dandb/hacklog.git
cd hacklog
cp .env.example .env
$EDITOR .env   # set HACKLOG_SMTP_USER, HACKLOG_SMTP_PASSWORD, HACKLOG_SMTP_SENDER,
               #     HACKLOG_ALERT_RECIPIENT (required)
```

### 2. Build and start

```bash
# Build the image
docker build -t hacklog:latest .

# Start the container
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

### 3. Verify

```bash
docker ps                    # STATUS should be "healthy"
docker logs hacklog          # inspect startup output
```

### 4. Send a test event

```bash
echo "<14>sshd[1234]: Accepted publickey for alice from 10.0.0.1 port 22 ssh2" \
  | nc -u -w1 127.0.0.1 10514
```

### Docker Compose (recommended for dev/test)

```bash
cp .env.example .env && $EDITOR .env
docker compose up -d
docker compose ps            # confirm healthy

# Optional: start with Prometheus monitoring
docker compose --profile monitoring up -d
# Prometheus UI → http://localhost:9091
```

---

## Quick Start — Bare Metal

### Prerequisites

- Python 3.12 or 3.13
- systemd 245+ (for service management)

### Install

```bash
git clone https://github.com/dandb/hacklog.git
cd hacklog
python -m venv .venv
source .venv/bin/activate
pip install .
```

### Configure and run

```bash
# Copy the example env file and fill in secrets
cp deploy/hacklog.env.example /etc/hacklog/hacklog.env
$EDITOR /etc/hacklog/hacklog.env

# Install and enable the systemd service
sudo cp deploy/hacklog.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hacklog

# Check status
sudo systemctl status hacklog
journalctl -u hacklog -f
```

---

## Configuration Reference

All configuration is supplied via environment variables. Values from `.env` / `--env-file` are loaded at startup. Environment variables always take precedence over YAML config file values.

### SMTP (required)

| Variable | Default | Description |
|----------|---------|-------------|
| `HACKLOG_SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `HACKLOG_SMTP_PORT` | `587` | SMTP server port |
| `HACKLOG_SMTP_USER` | *(required)* | SMTP authentication username |
| `HACKLOG_SMTP_PASSWORD` | *(required)* | SMTP authentication password |
| `HACKLOG_SMTP_SENDER` | *(required)* | From address for alert emails |
| `HACKLOG_ALERT_RECIPIENT` | *(required)* | Destination address for alert emails |

### Syslog Listener

| Variable | Default | Description |
|----------|---------|-------------|
| `HACKLOG_SYSLOG_BIND_ADDRESS` | `127.0.0.1` | UDP listener bind address |
| `HACKLOG_SYSLOG_PORT` | `10514` | UDP listener port |
| `HACKLOG_SYSLOG_MAX_MESSAGE_SIZE` | `2048` | Max syslog datagram size (bytes) |
| `HACKLOG_SYSLOG_RATE_LIMIT_PER_SOURCE` | `100` | Max messages per source IP per second |
| `HACKLOG_ALLOWED_CIDRS` | *(allow all)* | Comma-separated CIDR allowlist for syslog sources |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `HACKLOG_DATABASE_DB_URL` | `sqlite:///hacklog.db` | SQLAlchemy database URL |
| `HACKLOG_DATABASE_POOL_SIZE` | `5` | SQLAlchemy connection pool size |

### Data Retention

| Variable | Default | Description |
|----------|---------|-------------|
| `HACKLOG_EVENT_RETENTION_DAYS` | `365` | Days to retain event log records before physical deletion |
| `HACKLOG_PROFILE_INACTIVITY_DAYS` | `180` | Days of inactivity after which user profiles are purged |
| `HACKLOG_PURGE_SCHEDULE_HOUR` | `2` | UTC hour at which the daily purge runs (0–23) |
| `HACKLOG_PURGE_BATCH_SIZE` | `1000` | Records deleted per batch to avoid long SQLite transactions |

### Scoring Weights

All weights are integers in the range 0–100. Higher values make the corresponding dimension contribute more to the risk score.

| Variable | Default | Description |
|----------|---------|-------------|
| `HACKLOG_SCORING_HOURS_WEIGHT` | `10` | Weight for time-of-day anomaly |
| `HACKLOG_SCORING_DAYS_WEIGHT` | `10` | Weight for day-of-week anomaly |
| `HACKLOG_SCORING_SERVER_WEIGHT` | `15` | Weight for unusual server target |
| `HACKLOG_SCORING_SUCCESS_WEIGHT` | `35` | Weight for authentication failure |
| `HACKLOG_SCORING_VPN_WEIGHT` | `0` | Weight for VPN source IP |
| `HACKLOG_SCORING_INTERNAL_WEIGHT` | `10` | Weight for internal (RFC-1918) source IP |
| `HACKLOG_SCORING_EXTERNAL_WEIGHT` | `15` | Weight for external source IP |
| `HACKLOG_SCORING_IP_WEIGHT` | `15` | Weight for unusual source IP frequency |

### Alert Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `HACKLOG_SCORING_CRITICAL_THRESHOLD` | `50` | Score above which an alert is sent immediately |
| `HACKLOG_SCORING_SCARY_THRESHOLD` | `30` | Score above which the scare counter is incremented |
| `HACKLOG_SCORING_SCARE_COUNT_LIMIT` | `2` | Repeated scary events before an alert is triggered |
| `HACKLOG_SCORING_SCARE_DATE_EXPIRE_DAYS` | `1` | Days of inactivity before the scare counter resets |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `HACKLOG_METRICS_ENABLED` | `false` | Expose Prometheus `/metrics` endpoint |
| `HACKLOG_METRICS_PORT` | `9090` | HTTP port for the Prometheus metrics endpoint |
| `HACKLOG_DEAD_LETTER_PATH` | `dead_letter.jsonl` | Path for failed-alert dead-letter queue |

---

## Scoring Algorithm

Hacklog uses a **weighted surprisal model**: each authentication event is scored by measuring how unusual it is relative to the user's historical baseline. The final score is the sum of six dimension sub-scores.

### Dimensions

For each frequency-based dimension (time of day, day of week, server, source IP), the sub-score is calculated as:

```
sub_score = -log₂(frequency) × weight
```

Where `frequency` is the fraction of times this user has been seen with the given value (e.g., logging in on a Monday). A first-ever value has frequency near 0, producing a high sub-score. A frequently-seen value has frequency near 1, producing a sub-score near 0.

The remaining two dimensions are categorical:

| Dimension | Condition | Score |
|-----------|-----------|-------|
| **Authentication result** | Failure | +35 |
| **Authentication result** | Success | +0 |
| **IP location** | External | +15 |
| **IP location** | Internal (10.24.x, 10.26.x, 172.16.x) | +10 |
| **IP location** | VPN (10.42.x) | +0 |

### Alert Decision

After scoring, the engine decides what action to take:

```
score > CRITICAL (50)          → immediate alert email
score > SCARY (30)
  AND scare_count ≥ 2          → immediate alert email
score > SCARY (30)
  AND scare_count < 2          → increment scare counter
days since last scary ≥ 1     → reset scare counter
```

Every decision (score calculated, alert sent/suppressed, scare counter change) is persisted as an immutable audit record and emitted as a structured log entry.

### Example

A user who always logs in on weekdays from a known internal IP, then suddenly logs in on a Sunday from an unknown external IP with a failed password:

| Dimension | Value | Score |
|-----------|-------|-------|
| Auth failure | yes | +35 |
| External IP | new IP | +15 |
| Day of week | first Sunday | ~10 |
| Hour of day | unusual hour | ~5 |
| Server | familiar server | ~1 |
| Source IP | first external IP | ~15 |
| **Total** | | **~81 → CRITICAL alert** |

---

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for full setup instructions, code style guide, and PR process.

**Quick reference:**

```bash
git clone https://github.com/dandb/hacklog.git
cd hacklog
python -m venv .venv && source .venv/bin/activate
pip install -e '.[test,dev]'
pytest tests/

# Local server (requires .env with HACKLOG_SMTP_* secrets)
cp .env.example .env && make dev-start
make dev-stop   # graceful SIGTERM shutdown
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full setup instructions, code style guide, and PR process.

---

## License

Hacklog is released under the [GNU General Public License v3.0](LICENSE).
