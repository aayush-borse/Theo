# Architecture decision records

## ADR-001 — Modular monolith with independent workers

**Decision:** Keep HTTP API, domain orchestration, evaluation and provider adapters in one codebase; run optional Celery workers as a separate process. **Reason:** a solo-maintained project needs strong boundaries without microservice overhead. **Revisit when:** independent team ownership or resource isolation demonstrably requires service extraction.

## ADR-002 — Relational metadata and filesystem asset store

**Decision:** SQLAlchemy with SQLite for local development and PostgreSQL in Compose; binary assets remain outside SQL. **Reason:** convenient setup and transactional metadata. **Trade-off:** local filesystem storage is not HA shared object storage; a MinIO/S3 adapter remains a deployment extension.

## ADR-003 — Provider contract with modality-specific schemas

**Decision:** Each provider returns a common `Proposal` envelope while preserving modality/task-specific payloads. **Reason:** common job orchestration and traceability without pretending boxes, text spans, audio segments and table profiles share one schema. **Trade-off:** each task needs schema validation and task-specific metrics.

## ADR-004 — Human review and preserved predictions

**Decision:** Every automated proposal enters `REVIEW_REQUIRED`; original model output is preserved separately from corrected labels; each review decision is recorded. **Reason:** model output is a hypothesis, not ground truth. **Trade-off:** release requires explicit human review.

## ADR-005 — Gold references and reproducible evaluation

**Decision:** Independently verified labels are stored separately from predictions, with verifier and guideline version. Evaluation runs persist input parameters, reference version, results and exclusions. **Reason:** quality claims must be tied to a known reference set. **Trade-off:** representative sampling and independent annotation remain operator responsibilities.

## ADR-006 — Immutable release snapshots

**Decision:** A release stores a content-hashed manifest, quality report, sample hashes, original/current labels, provider metadata, review provenance and gold references. API write paths freeze released datasets; clone creates a new working dataset. **Reason:** reproducibility and auditability. **Trade-off:** privileged DB/storage operators can still alter bytes; production needs controlled access and external backups/integrity checks.

## ADR-007 — Optional specialist model dependencies

**Decision:** Keep heavyweight ML runtimes and checkpoints out of core installation. Enable Transformers, Ultralytics, Tesseract, faster-whisper and pyannote adapters through explicit configuration. **Reason:** hardware, model licences, checkpoint sizes and data-handling requirements differ substantially. **Trade-off:** optional integrations need separate environment-specific tests and model validation.

## ADR-008 — Authentication posture

**Decision:** Scrypt password hashing, expiring HS256 bearer tokens and admin/reviewer/viewer roles. Local loopback mode permits unauthenticated convenience; Docker Compose enables the auth gate. **Reason:** preserve zero-friction local evaluation while making the deployment profile safer by default. **Trade-off:** public deployment still requires HTTPS, secret management, proxy hardening and security review.

## ADR-009 — Durable distributed queue is optional

**Decision:** Local mode uses FastAPI background tasks; Compose runs Redis/Celery with a dedicated worker. **Reason:** low-friction local development and a path to durable queue execution. **Trade-off:** queue recovery, load tests, resource limits and monitoring must be validated in target deployment.
