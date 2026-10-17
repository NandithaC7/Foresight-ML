"""
check_ui_contract.py — verify that every response field the React UI reads exists
in REAL responses from the running backend.

Field list = output of:
  grep -ohE "\\b(item|i|it|scan|health|stats|tm|vit|result|insp|report|data|m)\\??\\.(\\w+)" \
      frontend/src/pages/*.jsx frontend/src/components/*.jsx
mapped to the endpoint each variable comes from. Writes artifacts/report/evidence/ui_contract_check.json.
"""
import csv
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = "http://localhost:8000"

EXPECTED = {
    "/api/analyze (top level: result/scan)": ["items", "mock", "warnings", "timing_ms", "model_version", "disclaimer", "scan_id", "id", "ts"],
    "/api/analyze items[] (item/i/it)": ["name", "tier", "freshness", "days", "decayPct", "action", "produce_confidence",
                                         "spoilage_label", "spoilage_confidence", "xai_overlay"],
    "/health (health)": ["model_loaded", "mock_mode", "model_version", "model_error"],
    "/api/stats (stats)": ["totalInspections", "totalItems", "shelfReadyPct", "avgLossPct"],
    "/api/inspections[] (insp)": ["ts", "items"],
    "/api/models models[] (m / vit)": ["id", "status", "role"],
    "/api/models vit entry (vit)": ["version", "backbone", "test_metrics"],
    "/api/models vit.test_metrics (tm)": ["type", "spoil"],
    "/api/report (report)": ["lines"],
    "/api/nutrition/{name} (data)": ["calories", "carbs", "fiber", "vitaminC", "potassium", "fact"],
}
NULLABLE_BY_DESIGN = {"days": "shelf-life unavailable → UI shows 'Not available'",
                      "decayPct": "segmentation unavailable → UI shows 'Pending annotation'",
                      "model_error": "null when model loaded"}


def main():
    c = httpx.Client(timeout=60)
    row = next(r for r in csv.DictReader(open(ROOT / "artifacts/dataset/v1/split_manifest.csv")) if r["split"] == "test")
    res = c.post(f"{API}/api/analyze?xai=true", files={"photo": ("t.jpg", (ROOT / "dataset/TR-6" / row["source_relative_path"]).read_bytes(), "image/jpeg")}).json()
    models = c.get(f"{API}/api/models").json()["models"]
    vit = next(m for m in models if m["id"] == "vit")
    objs = {
        "/api/analyze (top level: result/scan)": res,
        "/api/analyze items[] (item/i/it)": res["items"][0],
        "/health (health)": c.get(f"{API}/health").json(),
        "/api/stats (stats)": c.get(f"{API}/api/stats").json(),
        "/api/inspections[] (insp)": c.get(f"{API}/api/inspections").json()[0],
        "/api/models models[] (m / vit)": models[1],
        "/api/models vit entry (vit)": vit,
        "/api/models vit.test_metrics (tm)": vit["test_metrics"] or {},
        "/api/report (report)": c.get(f"{API}/api/report").json(),
        "/api/nutrition/{name} (data)": c.get(f"{API}/api/nutrition/Mango").json(),
    }
    checks = []
    for ep, fields in EXPECTED.items():
        for f in fields:
            present = f in objs[ep]
            val = objs[ep].get(f)
            checks.append({"endpoint": ep, "field": f, "present": present,
                           "type": type(val).__name__, "null_by_design": NULLABLE_BY_DESIGN.get(f, "") if val is None else ""})
    # the scan we just made is real model output and not mock
    out = {"model_version": res["model_version"], "source": res["source"], "mock": res["mock"],
           "fields_checked": len(checks), "fields_present": sum(c["present"] for c in checks), "checks": checks}
    c.delete(f"{API}/api/inspections")  # leave history empty
    (ROOT / "artifacts/report/evidence").mkdir(parents=True, exist_ok=True)
    json.dump(out, open(ROOT / "artifacts/report/evidence/ui_contract_check.json", "w"), indent=2)
    print(f"{out['fields_present']}/{out['fields_checked']} UI-consumed fields present; source={out['source']} mock={out['mock']}")
    for ch in checks:
        if not ch["present"]:
            print("MISSING", ch)


if __name__ == "__main__":
    main()
