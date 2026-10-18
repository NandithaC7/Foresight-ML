"""
main.py — Foresight backend (FastAPI)
=========================================
Serves real inference from the trained Foresight ViT checkpoint (see
inference.py). If the checkpoint is missing, /api/analyze returns HTTP 503
`model_unavailable` — it never fabricates predictions. Mock mode exists only
for UI development, is OFF by default (FORESIGHT_MOCK_MODE=1 to enable) and
every mock response is labelled "DEMO MOCK DATA".

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --port 8000

Docs (auto-generated): http://localhost:8000/docs
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

import config
import db
import inference
import mock_model
from schemas import AnalyzeResponse, Health

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "application/octet-stream"}


MODEL_FILES = (["foresight_vit_int8.onnx", "foresight_vit_meta.json", "unet_pilot.onnx", "unet_pilot_meta.json"] if config.RUNTIME == "onnx"
               else ["foresight_vit.pt", "unet_pilot.pt"]) + ["foresight_vit_test_metrics.json", "visible_decay_probe.json", "shelf_life_proxy.json"]


def fetch_models():
    """Download any missing model files from the Hugging Face repo in FORESIGHT_MODEL_REPO."""
    if not config.MODEL_REPO:
        return
    from huggingface_hub import hf_hub_download
    dest = config.MODEL_PATH.parent
    dest.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        if not (dest / name).exists():
            try:
                hf_hub_download(config.MODEL_REPO, name, local_dir=dest)
            except Exception as e:  # pragma: no cover - surfaced via /health and /api/models
                print(f"[startup] could not download {name}: {type(e).__name__}: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    fetch_models()
    db.init_db()
    inference.service.load()  # load weights once at startup
    yield


app = FastAPI(title="Foresight API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def api_error(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": {
        "code": "invalid_request", "message": "Request is missing the image file field 'photo'.",
        "errors": json.loads(json.dumps(exc.errors(), default=str))}})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):  # pragma: no cover
    return JSONResponse(status_code=500, content={"detail": {"code": "internal_error",
                                                             "message": "Unexpected server error."}})


# ---------------------------------------------------------------- status
def _health() -> dict:
    s = inference.service
    return {"status": "ok" if (s.ready or config.MOCK_MODE) else "degraded",
            "model_loaded": s.ready, "model_version": s.info.get("version"),
            "model_error": s.error, "mock_mode": config.MOCK_MODE, "device": s.info.get("device")}


@app.get("/health", response_model=Health)
def health_root():
    return _health()


@app.get("/api/health", response_model=Health)
def health():
    return _health()


@app.get("/api/models")
def models():
    s = inference.service
    metrics = None
    if config.MODEL_METRICS_PATH.exists():
        metrics = json.loads(config.MODEL_METRICS_PATH.read_text())
    return {
        "mock_mode": config.MOCK_MODE,
        "models": [
            {"id": "vit", "role": "produce type (6 classes) + spoilage (Spoiled / Not_spoiled) classification",
             "status": "loaded" if s.ready else "unavailable", "error": s.error, **s.info,
             "test_metrics": metrics,
             "confidence_note": "Softmax scores; calibration has not been evaluated."},
            {"id": "visible_decay", "role": "image-level visible-decay check (logistic probe on the ViT embedding, trained on human labels)",
             "status": "loaded" if getattr(s, "probe", None) else "unavailable", "error": getattr(s, "probe_error", None),
             **(getattr(s, "probe_info", None) or {}),
             "note": "Trained on 102 human image-level judgements; test n=29, so uncertainty is large."},
            ({"id": "unet", "role": "fruit + visible-decay segmentation (PILOT)", "status": "loaded", **s.unet_info,
              "reason": "PILOT trained on " + s.unet_info.get("mask_source", "") + " masks; demonstrates the pipeline, not a validated decay segmenter."}
             if getattr(s, "unet", None) else
             {"id": "unet", "role": "visible-decay segmentation", "status": "unavailable",
              "reason": "No trained U-Net yet: needs human-drawn decay polygons (" + str(getattr(s, "unet_error", "")) + ")"}),
            ({"id": "shelf_life", "role": "PROXY shelf-life regression (days until the TR-6 'Spoiled' label)", "status": "loaded", **s.shelf_info,
              "reason": "Proxy target derived from date-ordered dataset labels; not measured remaining shelf life."}
             if getattr(s, "shelf", None) else
             {"id": "shelf_life", "role": "shelf-life regression", "status": "disabled",
              "reason": "TR-6 has no measured time-to-endpoint labels (" + str(getattr(s, "shelf_error", "")) + ")"}),
            {"id": "yolo", "role": "multi-item detection", "status": "not_implemented",
             "reason": "TR-6 is single-item images with no bounding boxes; the app runs in single-item mode."},
            {"id": "dncnn", "role": "denoising (research experiment only)", "status": "not_in_inference_path"},
        ],
    }


# ---------------------------------------------------------------- analyze
async def _read_upload(photo: UploadFile) -> bytes:
    ctype = (photo.content_type or "").lower()
    if ctype and ctype not in ALLOWED_CONTENT_TYPES:
        api_error(415, "unsupported_media_type",
                  f"Unsupported file type '{ctype}'. Upload a JPG, PNG or WEBP photo.")
    limit = int(config.MAX_UPLOAD_MB * 1024 * 1024)
    chunks, size = [], 0
    while True:
        chunk = await photo.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            api_error(413, "file_too_large", f"File exceeds the {config.MAX_UPLOAD_MB:g} MB limit.")
        chunks.append(chunk)
    await photo.close()
    return b"".join(chunks)


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(photo: UploadFile = File(...), xai: bool = Query(False, description="Return an attention-rollout overlay")):
    data = await _read_upload(photo)
    try:
        image = await run_in_threadpool(inference.decode_image, data)
    except inference.ImageValidationError as e:
        api_error(400, "invalid_image", str(e))
    finally:
        del data  # uploaded bytes are never written to disk

    if config.MOCK_MODE:
        items = mock_model.simulate_analysis()
        meta = {"status": "ok", "source": "mock", "mock": True, "model_version": "DEMO-MOCK",
                "mode": "mock", "disclaimer": inference.DISCLAIMER, "timing_ms": {},
                "warnings": ["DEMO MOCK DATA — randomly simulated, not a model prediction."]}
        return db.insert_inspection(items, meta)

    svc = inference.service
    if not svc.ready:
        api_error(503, "model_unavailable", f"The analysis model is not loaded. {svc.error or ''}".strip())
    try:
        pred = await asyncio.wait_for(run_in_threadpool(svc.predict, image, xai), timeout=config.INFERENCE_TIMEOUT_S)
    except asyncio.TimeoutError:
        api_error(504, "inference_timeout", "Inference took too long. Please try again.")
    except Exception as e:  # pragma: no cover
        api_error(500, "inference_failed", f"Inference failed: {type(e).__name__}")

    item, warnings = inference.compose_item(pred, svc.info["produce_classes"], xai)
    warnings += [
        "Single-item mode: the whole photo is treated as one item (no object detection).",
        "Trained on TR-6 lab photos (one fruit, plain background); other scenes may be unreliable.",
        ("Shelf-life is a PROXY estimate (days until the dataset's 'Spoiled' label, test MAE about 4 days) — not a measured shelf life. "
         if getattr(svc, "shelf", None) else "Shelf-life is unavailable (no validated labels). ") + ("Decay coverage comes from a PILOT U-Net trained on machine-generated masks — indicative only."
            if getattr(svc, "unet", None) else "Decay-area segmentation is pending human mask annotation."),
    ]
    meta = {"status": "ok", "source": "model", "mock": False, "model_version": svc.info["version"],
            "mode": "single_item", "disclaimer": inference.DISCLAIMER,
            "timing_ms": {"inference": round(pred["inference_ms"], 1)}, "warnings": warnings}
    return db.insert_inspection([item], meta)


# ---------------------------------------------------------------- history
@app.get("/api/history")
def history(limit: int = Query(100, ge=1, le=1000)):
    return db.get_inspections(limit)


@app.get("/api/history/{scan_id}")
def history_item(scan_id: str):
    rec = db.get_inspection(scan_id)
    if not rec:
        api_error(404, "not_found", f"No scan with id '{scan_id}'.")
    return rec


@app.get("/api/inspections")
def list_inspections():
    return db.get_inspections()


@app.delete("/api/inspections")
def reset_inspections():
    db.clear_inspections()
    return {"cleared": True}


@app.get("/api/stats")
def stats():
    return db.compute_stats()


@app.get("/api/nutrition/{crop_name}")
def nutrition(crop_name: str):
    data = mock_model.NUTRITION.get(crop_name)
    if not data:
        api_error(404, "not_found", f"No nutrition data for '{crop_name}'")
    return {"name": crop_name, **data}


@app.get("/api/tips")
def tips():
    return mock_model.TIPS


# ---------------------------------------------------------------- report
def _build_report_lines() -> list[str]:
    """Template-based summary of stored scans (no LLM involved)."""
    inspections = db.get_inspections()
    items = [it for insp in inspections for it in insp["items"]]
    s = db.compute_stats()

    if not inspections:
        return ["No data yet — run a scan on the Analyze page."]

    by_tier = {"good": 0, "warn": 0, "bad": 0}
    for i in items:
        by_tier[i.get("tier", "warn")] += 1
    flagged = sorted({i["name"] for i in items if i.get("tier") == "bad"})
    mock_scans = sum(1 for insp in inspections if insp.get("source") == "mock")
    versions = sorted({insp.get("model_version") for insp in inspections if insp.get("model_version")})

    lines = [
        "FORESIGHT - INSPECTION SUMMARY",
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Model version(s): {', '.join(versions) if versions else 'unknown'}",
        "",
        f"Total inspections run: {s['totalInspections']}",
        f"Total items analysed: {s['totalItems']}",
        f"No spoilage cues: {s['shelfReadyPct']}%   Spoiled: {s['avgLossPct']}%",
        "",
        "Breakdown (model prediction):",
        f"  Not spoiled:  {by_tier['good']}",
        f"  Uncertain:    {by_tier['warn']}",
        f"  Spoiled:      {by_tier['bad']}",
        "",
        f"Items flagged as spoiled: {', '.join(flagged) if flagged else 'none currently'}",
        "",
        "Visual estimate only - not a food-safety guarantee. Shelf-life is not",
        "estimated (no validated labels). Inspect uncertain items manually.",
    ]
    if mock_scans:
        lines.append(f"WARNING: {mock_scans} scan(s) are DEMO MOCK DATA, not model predictions.")
    return lines


@app.get("/api/report")
def report_text():
    return {"lines": _build_report_lines()}


@app.get("/api/report/pdf")
def report_pdf():
    from fpdf import FPDF

    lines = _build_report_lines()
    inspections = db.get_inspections()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(47, 74, 61)
    pdf.cell(0, 10, "Foresight - Inspection Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(203, 190, 149)
    pdf.line(10, 20, 200, 20)
    pdf.ln(6)

    pdf.set_font("Courier", "", 10)
    pdf.set_text_color(20, 20, 20)
    for line in lines:
        pdf.set_x(10)
        if line == "":
            pdf.ln(4)
        else:
            pdf.multi_cell(0, 6, line.encode("latin-1", "replace").decode("latin-1"), new_x="LMARGIN", new_y="NEXT")

    rows = [
        (datetime.fromtimestamp(insp["ts"] / 1000).strftime("%Y-%m-%d %H:%M"), it["name"],
         it.get("spoilage_label") or it.get("tier"), it.get("freshness"), insp.get("source", "?"))
        for insp in inspections for it in insp["items"]
    ][:30]

    if rows:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Full scan log", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for r in rows:
            pdf.set_x(10)
            pdf.cell(0, 6, f"{r[0]}   {r[1]}   {r[2]}   not-spoiled score {r[3]}%   [{r[4]}]",
                     new_x="LMARGIN", new_y="NEXT")

    pdf_bytes = bytes(pdf.output())
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=foresight-report.pdf"},
    )
