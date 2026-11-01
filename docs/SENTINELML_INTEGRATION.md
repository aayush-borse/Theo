# SentinelML handoff contract

THEO and SentinelML have deliberately separate responsibilities:

- **THEO:** ingest data, generate annotation proposals, validate structures, capture evidence/provenance, manage human review, curate gold references, evaluate annotation quality and publish immutable dataset releases.
- **SentinelML:** consume a released dataset, run its own schema/data checks, train/evaluate models, apply model quality gates, register/serve approved models and monitor drift.

THEO does not train or monitor models and does not modify SentinelML model artifacts.

## Export flow

1. Complete annotation and human review in THEO.
2. Create an immutable dataset release.
3. Select **SentinelML handoff ZIP** from the dataset's Quality & releases panel, or call `GET /api/datasets/{id}/export/sentinelml`.
4. THEO produces a ZIP with:
   - `manifest.json`: contract name `theo.sentinelml.dataset.v1`, release ID/version/hash, dataset modality/task and quality snapshot.
   - `records.jsonl`: approved sample records with source hashes, labels, provider and evidence metadata.
   - `quality_report.json`: THEO release-time quality report.
   - `assets/`: original sample assets referenced by approved records.
5. SentinelML verifies the release hash and source asset hashes, validates its own ingestion schema and then starts its independent training/evaluation pipeline.

## Why this is a file contract first

No stable SentinelML ingestion endpoint, authentication scheme or payload schema was supplied as part of this repository. A direct remote push would require guessing those contracts and could create a brittle or unsafe integration. The versioned bundle is a concrete interoperability boundary that can be consumed manually or by a future connector once SentinelML's real API contract is available.
