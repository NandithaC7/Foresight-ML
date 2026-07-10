"""
main.py — Foresight backend (FastAPI)
=========================================
Mock backend: no real ML model is wired in yet (see mock_model.py). Every
endpoint's shape is designed to stay the same once a real model is plugged
in, so the frontend never has to change.

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Docs (auto-generated): http://localhost:8000/docs
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from datetime import datetime
from io import BytesIO

import db
import mock_model

app = FastAPI(title="Foresight API", version="0.1.0")

# CORS: wide open for local dev / demo purposes. Before a real deployment,
# replace "*" with your actual frontend URL(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(photo: UploadFile = File(...)):
    """
    Accepts an uploaded produce photo. Currently ignores the actual image
    content and returns simulated results (see mock_model.py). Once a real
    detection/classification pipeline exists, read `await photo.read()` here
    and run it through that pipeline instead — the response shape stays the same.
    """
    _ = await photo.read()  # image bytes available here once a real model exists
    items = mock_model.simulate_analysis()
    saved = db.insert_inspection(items)
    return saved


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
        raise HTTPException(status_code=404, detail=f"No nutrition data for '{crop_name}'")
    return {"name": crop_name, **data}


@app.get("/api/tips")
def tips():
    return mock_model.TIPS


def _build_report_lines() -> list[str]:
    inspections = db.get_inspections()
    items = [it for insp in inspections for it in insp["items"]]
    s = db.compute_stats()

    if not inspections:
        return ["No data yet — run a scan on the Analyze page."]

    by_tier = {"good": 0, "warn": 0, "bad": 0}
    for i in items:
        by_tier[i["tier"]] += 1
    flagged = sorted({i["name"] for i in items if i["tier"] == "bad"})

    lines = [
        "FORESIGHT - INSPECTION SUMMARY",
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Total inspections run: {s['totalInspections']}",
        f"Total items analysed: {s['totalItems']}",
        f"Shelf-ready: {s['shelfReadyPct']}%   Avg loss: {s['avgLossPct']}%",
        "",
        "Breakdown:",
        f"  Fresh (>=85%):      {by_tier['good']}",
        f"  Use soon (60-84%):  {by_tier['warn']}",
        f"  Discarded (<60%):   {by_tier['bad']}",
        "",
        f"Items flagged for removal: {', '.join(flagged) if flagged else 'none currently'}",
        "",
        "Recommendation: prioritise 'use soon' items for discount or immediate",
        "use before they cross into the discard range on the next check.",
    ]
    return lines


@app.get("/api/report")
def report_text():
    """Plain-text report summary — template-based, not a live LLM call.
    To generate this with a real LLM instead: send this same stats/items
    payload to the Claude/OpenAI API from here (server-side, where your API
    key is safe), and return the model's text instead of _build_report_lines()."""
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
            pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")

    rows = [
        (datetime.fromtimestamp(insp["ts"] / 1000).strftime("%Y-%m-%d %H:%M"), it["name"], it["freshness"], it["days"], it["tier"])
        for insp in inspections for it in insp["items"]
    ][:30]

    if rows:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Full scan log", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for r in rows:
            pdf.set_x(10)
            pdf.cell(0, 6, f"{r[0]}   {r[1]}   {r[2]}%   {r[3]}d   {r[4]}", new_x="LMARGIN", new_y="NEXT")

    pdf_bytes = bytes(pdf.output(dest="S"))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=foresight-report.pdf"},
    )
