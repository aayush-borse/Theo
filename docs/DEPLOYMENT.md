# Deployment and operations

## Local development

Use `START_WINDOWS.bat` or `START.sh`. These create a virtual environment, generate a local JWT secret in `.env`, install core dependencies and launch Uvicorn bound to loopback. Local mode defaults to SQLite, in-process background tasks and optional authentication.

## Docker Compose profile

1. Copy `.env.example` to `.env`.
2. Generate a strong secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Set `THEO_JWT_SECRET` and `POSTGRES_PASSWORD` in `.env`.
4. Optionally set `THEO_INSTALL_ML=true` to build the larger image with optional inference dependencies.
5. Run `docker compose up --build`.
6. Open `http://localhost:8000`, create the first administrator and sign in.

Compose runs FastAPI, PostgreSQL, Redis and a Celery worker. Schema migrations are applied on application startup through Alembic (`THEO_AUTO_MIGRATE=true`). The worker waits for the API health check before starting.

## Operations checks

- Liveness: `GET /api/health`
- Readiness/database check: `GET /api/health/ready`
- API documentation: `/docs`
- Job queue: inspect `/api/jobs`; in Compose also monitor Celery worker and Redis health.
- Data volumes: `theo_data` holds original assets/exports; `postgres_data` holds relational metadata.

## Backup and recovery

Back up PostgreSQL and the `theo_data` volume together. A database-only backup is insufficient because manifests refer to original assets. Test restores in an isolated environment and verify SHA-256 hashes from release manifests. Define retention and deletion policy before storing personal or regulated data.

## Production hardening

Do not expose the Compose port directly to the internet. Put it behind HTTPS and a reverse proxy with request/body limits. Restrict network access to PostgreSQL/Redis, use a secrets manager, set exact CORS origins, enable upload scanning, constrain worker CPU/memory/GPU, monitor queue depth/failures, run dependency/container scans and conduct security/load/recovery tests. Add object storage if multi-host scale or high availability is required.
