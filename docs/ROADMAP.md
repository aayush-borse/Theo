# Product scope and engineering status

This repository contains a broad, integrated implementation of the THEO platform scope. Optional model-backed capabilities are enabled through separately installed dependencies and configured checkpoints; no large pretrained weights are bundled in the source archive.

## Implemented in this distribution

- Six modality ingestion and provider pipelines.
- Optional image classification, YOLO detection/segmentation when checkpoint supports masks, text sentiment/NER, scanned-PDF OCR, audio transcription/diarization and video object tracking.
- Evidence/provenance capture and human review decisions.
- Gold-label registry and persisted evaluation runs.
- Classification metrics, ECE, Cohen's kappa, nominal Krippendorff alpha and descriptive explicit-group audit.
- Dataset release manifests with hashes, release freeze and clone-to-revise workflow.
- JSONL/CSV/manifest, COCO JSON and YOLO ZIP exports.
- Scrypt password hashing, expiring bearer tokens, role gate and first-admin bootstrap.
- Local jobs and optional Redis/Celery workers.
- Alembic schema migration, Docker Compose, CI tests and responsive browser UI.

## Remaining production validation (not a hidden MVP backlog)

A codebase cannot certify its own production fitness. Before real customer or regulated-data deployment, operators must perform and document:

1. Security review, threat-model validation, dependency/container scanning and penetration testing.
2. Load, concurrency, queue recovery and large-file performance tests on target hardware.
3. Backup/restore and disaster-recovery drills.
4. Object-storage adapter and lifecycle/retention controls if local filesystem storage is insufficient.
5. Task-specific gold benchmarks for every selected model/checkpoint and modality.
6. Model licence, data privacy, consent and acceptable-use review.
7. Detection/segmentation, NER, OCR, diarization and tracking evaluation suites appropriate to deployed tasks.
8. Deployment-specific observability, alerting, secrets management and HTTPS configuration.

These are validation and deployment responsibilities, not features to fake with placeholder outputs. The current project exposes the corresponding extension points and operational documentation where feasible.
