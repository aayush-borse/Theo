# Model integration matrix

THEO keeps heavyweight model runtimes optional. Core ingestion, review, evaluation, release and export workflows run without downloading neural checkpoints. Provider code reads model references from environment variables and returns explicit inference errors/limitations rather than silently claiming success.

| Modality | Implemented adapter | Config | Output | Known limitation |
|---|---|---|---|---|
| Image | Hugging Face image-classification pipeline | `THEO_IMAGE_CLASSIFIER_MODEL` | ranked class predictions and model scores | Scores are not calibrated probabilities; validate on gold data |
| Image | Ultralytics YOLO | `THEO_YOLO_MODEL` | class, confidence, pixel xyxy boxes; mask polygons when model yields masks | Segmentation only with segmentation checkpoint; not all checkpoints support masks |
| Text | Transformers sentiment pipeline | `THEO_SENTIMENT_MODEL` | label and reported score | Domain, language and calibration limitations depend on checkpoint |
| Text | Transformers token-classification pipeline | `THEO_NER_MODEL` | entity text, class, score and character offsets | Tokenization/offset behavior must be validated for chosen model and language |
| Document | PyMuPDF | Core dependency | per-page text and page metadata | Text layer only; scanned pages need OCR |
| Document | Tesseract OCR | `THEO_ENABLE_OCR=true` plus system Tesseract | OCR text on pages with little text-layer content | OCR is noisy; layout/table reconstruction not guaranteed |
| Tabular | Deterministic CSV profiler | Core | type inference, missingness, uniqueness, duplicates, IQR flags | Statistical signals do not determine domain validity |
| Audio | faster-whisper | `THEO_WHISPER_MODEL` | language metadata and timestamped transcript segments | Model size, codec support and CPU/GPU runtime affect throughput |
| Audio | pyannote.audio | `THEO_DIARIZATION_MODEL`, `HF_TOKEN` as required | speaker turns with timestamps | Model terms/access restrictions; speaker identity is not inferred |
| Video | OpenCV | Core optional runtime in ML extra | frame sampling and timestamps | No semantic activity recognition |
| Video | Ultralytics persistent tracking | `THEO_YOLO_MODEL` | frame-level detections and track IDs | Track fragmentation, occlusion and camera cuts; not action recognition |

## Explicitly not claimed

- Universal semantic understanding across all modalities.
- 100% annotation accuracy, zero hallucinations or zero bias.
- Calibrated confidence merely because a provider reports a score.
- Human-level speaker identification, biometric identification or emotion diagnosis.
- High-level video action recognition in the current provider.
- Guaranteed table structure recovery from complex PDFs.
- Fairness certification from descriptive subgroup-rate differences.

Every optional model integration must be validated with task-specific gold data, version-pinned, licence-reviewed and run in a suitable resource-isolated worker before production use.
