# Changelog

## 1.1.0 — 2026-11-01

- Reframed THEO as Trusted Evidence-based Annotation & Quality Orchestration.
- Added optional pretrained model adapters for image classification, YOLO detection/segmentation, Transformers sentiment/NER, Tesseract OCR, faster-whisper transcription, pyannote diarization and YOLO video tracking.
- Expanded tabular profiling with duplicate rows, missingness, descriptive numeric statistics and IQR outlier flags.
- Added persisted independently verified gold labels and gold-standard classification evaluation runs.
- Added ECE, Cohen's kappa, nominal Krippendorff alpha and explicit-group descriptive subgroup audits.
- Added review-decision history, adjudication and release manifest provenance.
- Enforced application-level release immutability and clone-to-revise workflows.
- Added COCO JSON and YOLO ZIP exports.
- Added scrypt password hashing, expiring bearer tokens, first-admin bootstrap and role-aware API gate.
- Added optional Redis/Celery workers, PostgreSQL Compose profile and Alembic migrations.
- Added Evaluation Lab and gold-reference UI workflows.
- Expanded tests and documentation for scientific and deployment boundaries.

## 1.0.0

- Initial local-first dataset registry, ingestion, baseline providers, human review, quality reports, releases and glass-inspired frontend.
