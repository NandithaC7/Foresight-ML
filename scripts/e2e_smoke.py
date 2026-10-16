"""
e2e_smoke.py — local end-to-end smoke test against RUNNING servers.

Checks: frontend serves the app, backend health reports a loaded real model,
CORS allows the frontend origin, real held-out TR-6 test images are analysed,
errors are well-formed, history persists, and latency is recorded.
Writes artifacts/report/evidence/e2e_smoke.json and latency_benchmark.json.

Usage: .venv/bin/python scripts/e2e_smoke.py [--api http://localhost:8000] [--ui http://localhost:5173]
"""
import argparse
import csv
import datetime as dt
import json
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "artifacts/report/evidence"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--ui", default="http://localhost:5173")
    ap.add_argument("--n", type=int, default=60, help="held-out test images to send")
    a = ap.parse_args()
    EVID.mkdir(parents=True, exist_ok=True)
    checks, c = [], httpx.Client(timeout=60)

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))

    ui = c.get(a.ui)
    check("frontend serves index.html", ui.status_code == 200 and '<div id="root">' in ui.text, f"HTTP {ui.status_code}")
    h = c.get(f"{a.api}/health").json()
    check("backend health: real model loaded, mock off", h["model_loaded"] and not h["mock_mode"], h.get("model_version"))
    pre = c.options(f"{a.api}/api/analyze", headers={"Origin": a.ui, "Access-Control-Request-Method": "POST"})
    check("CORS preflight allows frontend origin", pre.headers.get("access-control-allow-origin") == a.ui)
    models = c.get(f"{a.api}/api/models").json()["models"]
    check("/api/models reports ViT loaded and U-Net unavailable",
          {m["id"]: m["status"] for m in models}.get("vit") == "loaded" and
          {m["id"]: m["status"] for m in models}.get("unet") == "unavailable")

    rows = [r for r in csv.DictReader(open(ROOT / "artifacts/dataset/v1/split_manifest.csv")) if r["split"] == "test"]
    rows = sorted(rows, key=lambda r: r["sha256"])[:: max(1, len(rows) // a.n)][: a.n]
    before = len(c.get(f"{a.api}/api/history?limit=1000").json())
    lat, ok_t, ok_s, scan_ids = [], 0, 0, []
    for r in rows:
        data = (ROOT / "dataset/TR-6" / r["source_relative_path"]).read_bytes()  # full-resolution original
        t0 = time.perf_counter()
        res = c.post(f"{a.api}/api/analyze", files={"photo": ("p.jpg", data, "image/jpeg")}, headers={"Origin": a.ui})
        lat.append((time.perf_counter() - t0) * 1000)
        if res.status_code != 200:
            check(f"analyze {r['sample_id']}", False, res.text[:200]); continue
        body = res.json(); it = body["items"][0]; scan_ids.append(body["scan_id"])
        ok_t += it["produce_class"] == r["produce_class"]
        ok_s += (it["spoilage_label"] == "Spoiled") == (r["source_label"] == "Spoiled")
    check(f"analysed {len(scan_ids)}/{len(rows)} held-out source images via HTTP", len(scan_ids) == len(rows),
          f"produce correct {ok_t}/{len(rows)}, spoilage correct {ok_s}/{len(rows)} (full-res originals through API)")
    after = c.get(f"{a.api}/api/history?limit=1000").json()
    check("history grew by the number of scans", len(after) - before == len(scan_ids), f"{before} -> {len(after)}")
    one = c.get(f"{a.api}/api/history/{scan_ids[0]}") if scan_ids else None
    check("history detail endpoint returns the scan", one is not None and one.status_code == 200)
    x = c.post(f"{a.api}/api/analyze?xai=true", files={"photo": ("p.jpg", (ROOT / "dataset/TR-6" / rows[0]["source_relative_path"]).read_bytes(), "image/jpeg")})
    check("XAI overlay returned", x.status_code == 200 and x.json()["items"][0]["xai_overlay"].startswith("data:image/png"))
    bad = c.post(f"{a.api}/api/analyze", files={"photo": ("a.txt", b"not an image", "text/plain")})
    check("wrong file type rejected with 415 + structured error", bad.status_code == 415 and bad.json()["detail"]["code"] == "unsupported_media_type")
    cor = c.post(f"{a.api}/api/analyze", files={"photo": ("a.jpg", b"\xff\xd8garbage", "image/jpeg")})
    check("corrupt image rejected with 400", cor.status_code == 400 and cor.json()["detail"]["code"] == "invalid_image")
    pdf = c.get(f"{a.api}/api/report/pdf")
    check("PDF report generated", pdf.status_code == 200 and pdf.content[:4] == b"%PDF")

    summary = {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "api": a.api, "ui": a.ui,
               "model_version": h.get("model_version"), "device": h.get("device"), "checks": checks,
               "passed": sum(x["pass"] for x in checks), "total": len(checks),
               "held_out_images_via_api": len(rows), "produce_correct": ok_t, "spoilage_correct": ok_s}
    json.dump(summary, open(EVID / "e2e_smoke.json", "w"), indent=2)
    json.dump({"device": h.get("device"), "note": "end-to-end HTTP latency incl. upload of ~1.9 MB full-res JPEG, decode, resize, ViT-B inference, SQLite write",
               "samples_ms": lat, "median_ms": statistics.median(lat), "p95_ms": sorted(lat)[int(0.95 * len(lat)) - 1]},
              open(EVID / "latency_benchmark.json", "w"), indent=2)
    print(f"{summary['passed']}/{summary['total']} checks passed; median latency {statistics.median(lat):.0f} ms")


if __name__ == "__main__":
    main()
