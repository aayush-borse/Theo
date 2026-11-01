# Quality methodology

THEO reports observable evidence and keeps independent quality dimensions separate.

## Annotation-level signals

- Structural validity: does the output satisfy the selected schema and modality contract?
- Evidence completeness: can the proposal be traced to the source sample, page, span, frame, region or timestamp?
- Provider-reported score: what did the model report? This is not automatically a probability or accuracy estimate.
- Human decision: approved, rejected, corrected or adjudicated, with reviewer and timestamp.
- Provenance: provider/model version, parameters where available, source hash and audit events.

## Gold-standard evaluation

Curate a representative, independently verified reference set with written annotation guidelines and adjudication policy. Keep it separate from the model-generated proposal set. Report at minimum:

- Classification: accuracy, per-class precision/recall/F1 and confusion matrix.
- Confidence: expected calibration error (ECE) over stated bins, alongside reliability plots and sample counts in a full evaluation report.
- Two annotators: Cohen's kappa where assumptions and task structure are appropriate.
- Multiple annotators: Krippendorff's alpha nominal for categorical labels; select another distance function for ordinal/continuous tasks rather than reusing nominal alpha.
- Object detection/segmentation: use task-specific IoU, precision/recall and mAP calculations from a validated evaluation stack; not inferred from generic classification metrics.
- NER: span-level exact/overlap precision, recall and F1 with a documented offset/tokenization convention.

The API implements core classification, ECE, Cohen's kappa and nominal Krippendorff alpha utilities. Modality-specific benchmark pipelines should be added for each deployed task; do not compare unlike tasks using one scalar.

## Agreement is not correctness

High inter-annotator agreement can coexist with shared systematic error. Resolve disagreement using documented guidelines and adjudication. Report missing ratings and unit counts; do not hide excluded pairs.

## Subgroup analysis

THEO's subgroup endpoint accepts group values explicitly supplied by the operator and returns descriptive outcome rates, label distributions and maximum rate difference. It does not infer sensitive attributes. Review sample sizes, confidence intervals, legitimate task context, label quality, base rates and applicable law with domain experts. A raw rate difference is a signal, not a fairness verdict.

## Release gate

A release is blocked when samples lack annotations or proposals remain unresolved/rejected. Released dataset manifests include sample hashes and annotation snapshots. The source dataset is frozen by application workflows; create a working clone to make changes. Release hash integrity does not protect against privileged database/storage tampering, so use access control, backups and external integrity verification in production.
