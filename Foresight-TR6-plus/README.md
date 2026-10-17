# Foresight-TR6+

Phase 1 workspace for a provenance-aware, human-annotated extension of TR-6.

This workspace does not contain the original 20+ GB dataset, does not alter source files and currently contains no completed annotations.

## Layout

- `config/`: deterministic build policy.
- `scripts/`: manifest generation and validation.
- `manifests/`: master, pilot and exclusion records.
- `imports/`: annotation-tool task/configuration templates.
- `annotations/`: pending annotation ledger and empty COCO scaffold.
- `docs/`: protocol, data dictionary, design and publication questions.
- `reports/`: machine-readable summaries and local review contact sheets.
- `checksums/`: hashes for extension artifacts.

## Source references

- Original dataset: `../TR-6`
- Audit outputs: `../dataset-preparation/tr6-audit/output`

Both are external to this extension workspace.

## Rebuild

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_extension.py \
  --dataset ../TR-6 \
  --audit-output ../dataset-preparation/tr6-audit/output \
  --workspace . \
  --seed 20261012 \
  --per-produce-modality 8
```

## Validate

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_extension.py \
  --dataset ../TR-6 \
  --workspace . \
  --hash-mode pilot
```

`hash-mode pilot` recomputes SHA-256 for the 96 selected images. Use `all` only when a full 20+ GB source recheck is intentionally required.

## Annotation start

Read `docs/annotation_protocol.md` before importing `imports/label_studio_tasks.json` and `imports/label_studio_config.xml`. All 96 tasks begin as `pending`.
