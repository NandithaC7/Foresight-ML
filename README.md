# Foresight — visual produce-spoilage estimation (React + FastAPI + ViT)

Research prototype. Upload a photo of **one** banana, carrot, guava, Indian
gooseberry, mango or tomato; a fine-tuned Vision Transformer predicts the produce
type and whether it shows visible spoilage cues, with an attention-rollout
heat-map. **Visual estimate — not a food-safety guarantee.**

```
foresight/
├── dataset/TR-6/            original dataset (read-only, never modified)
├── dataset-preparation/     TR-6 audit scripts + outputs (original + 2026-10-15 re-run)
├── Foresight-TR6-plus/      earlier provenance/annotation package (unchanged)
├── ml/                      split, training, evaluation, experiments, tests
├── artifacts/               split manifests, runs (checkpoints, logs, metrics), experiments, report figures/tables
├── backend/                 FastAPI inference API + SQLite history + tests
├── frontend/                React (Vite) UI
└── docs/                    progress report, dataset/model cards, test report, experiment log
```

Start with **[docs/PROGRESS_REPORT.md](docs/PROGRESS_REPORT.md)**. It lists what works, the real metrics, and what remains incomplete.

## 1. Environment (macOS / Linux, Python 3.11, Node 18+)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r ml/requirements.txt      # includes backend/requirements.txt
cd frontend && npm install && cd ..
```

## 2. Run the application

The backend loads `backend/models/foresight_vit.pt`, which is a copy of
`artifacts/runs/vit_b16_primary/best.pt`. If that file is missing, `/api/analyze`
returns HTTP 503 `model_unavailable`. It never returns made-up predictions.

```bash
cd backend && ../.venv/bin/uvicorn main:app --port 8000          # terminal 1
cd frontend && cp -n .env.example .env && npm run dev            # terminal 2
```

Open http://localhost:5173. API docs: http://localhost:8000/docs.

Production build of the UI: `cd frontend && npm run build && npm run preview` (served on :4173, which is already in the CORS list).

Configuration is through environment variables; see `backend/.env.example` and use `uvicorn main:app --env-file .env`.
Mock mode (`FORESIGHT_MOCK_MODE=1`) is for UI work only. It is off by default, and every response it produces is labelled **DEMO MOCK DATA**.

## 3. API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health`, `/api/health` | service status, `model_loaded`, model version, mock flag |
| GET | `/api/models` | status of every model (ViT loaded; U-Net/shelf-life/YOLO unavailable, with reasons) + test metrics |
| POST | `/api/analyze?xai=true` | multipart field `photo` (JPG/PNG/WEBP, ≤15 MB) → one item with produce type, spoilage, confidences, XAI overlay |
| GET | `/api/history`, `/api/history/{scan_id}` | persisted scans (SQLite; images are not stored) |
| GET/DELETE | `/api/inspections` | legacy list / clear used by the UI |
| GET | `/api/stats`, `/api/report`, `/api/report/pdf`, `/api/tips`, `/api/nutrition/{name}` | dashboard, report, static content |

Errors use the shape `{"detail": {"code": "...", "message": "..."}}`. The codes are `unsupported_media_type` (415), `file_too_large` (413),
`invalid_image` (400), `invalid_request` (422), `model_unavailable` (503), `inference_timeout` (504) and `not_found` (404).

## 4. Reproduce the ML pipeline

```bash
# audit (read-only) → split → image cache
python3 dataset-preparation/tr6-audit/audit_tr6.py --dataset dataset/TR-6 --output dataset-preparation/tr6-audit/output_rerun_2026-10-15
python3 ml/data/make_splits.py --inventory dataset-preparation/tr6-audit/output_rerun_2026-10-15/file_inventory.csv --out artifacts/dataset/v1 --seed 42
python3 ml/data/build_cache.py --manifest artifacts/dataset/v1/split_manifest.csv --dataset dataset/TR-6 --out artifacts/cache/srgb_256
# train + evaluate the primary model (test split is read only by evaluate_vit.py)
.venv/bin/python ml/train/train_vit.py --run-id vit_b16_primary --epochs 12 --patience 4
.venv/bin/python ml/evaluate/evaluate_vit.py --run artifacts/runs/vit_b16_primary --split test
cp artifacts/runs/vit_b16_primary/best.pt backend/models/foresight_vit.pt
cp artifacts/runs/vit_b16_primary/eval/test_clean_0_none.json backend/models/foresight_vit_test_metrics.json
```

The experiment commands (robustness, DnCNN, GAN, K-means, XAI, ablations, figures) are in [docs/EXPERIMENT_LOG.md](docs/EXPERIMENT_LOG.md).

## 5. Tests

```bash
.venv/bin/python -m pytest backend/tests ml/tests -q
cd frontend && npm run build
.venv/bin/python scripts/e2e_smoke.py       # starts nothing; expects backend on :8000 and frontend on :5173
```

## Hosting

The frontend `dist/` can be deployed to any static host. The backend needs a Python host with about 1.5 GB RAM, because the ViT-B checkpoint is 343 MB and runs on CPU there.
Set `FORESIGHT_CORS_ORIGINS` to the deployed frontend URL and `VITE_API_BASE` to the backend URL. No third-party deployment has been performed yet.
