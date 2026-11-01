# Build verification record

Validated while preparing this archive:

- Backend automated tests: **15 passed**.
- Python source and migration modules: compile/AST checks passed.
- Frontend JavaScript: `node --check frontend/app.js` passed.
- Alembic: fresh SQLite database migrated to head; all expected tables created.
- Runtime smoke test: Uvicorn started; `/api/health`, `/api/health/ready`, `/api/capabilities` and `/` returned HTTP 200.
- Workflow coverage includes dataset upload, annotation jobs, human review, schema-validation gate, immutable release/clone, COCO/YOLO/SentinelML export, gold-label evaluation, calibration/agreement metrics, auth bootstrap and adjudication constraints.

Not verified in this build environment:

- Docker Compose build/start, because Docker is not installed in the build environment.
- GPU inference, model downloads, model accuracy or third-party model licence/terms.
- Production security, penetration, load, failover, backup/restore or disaster-recovery testing.
- Remote SentinelML API push. THEO provides a versioned release handoff ZIP because no SentinelML endpoint/authentication contract was supplied.

A passing local test suite verifies the tested workflows; it is not a production certification or proof of model quality.
