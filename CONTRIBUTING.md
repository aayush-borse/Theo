# Contributing

Thanks for helping improve THEO. The project values correctness, explicit limitations, reproducibility and readable code over clever abstractions.

## Development setup

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend pytest backend/tests -q
node --check frontend/app.js
```

## Engineering expectations

- Explain the user problem and expected behaviour in the issue/PR.
- Keep modality-specific logic behind `AnnotationProvider`.
- Never auto-approve generated labels.
- Do not represent confidence as accuracy.
- Preserve provenance and record consequential state changes.
- Add tests for failure paths, not only happy paths.
- Do not commit secrets, uploaded datasets, model weights or private data.
- Update docs when changing API, data model, provider behaviour or security boundaries.

## Pull requests

Include scope, design rationale, tests run, screenshots for UI changes, migration/API compatibility notes and known limitations. Large architectural changes should include an ADR in `docs/decisions/`.
