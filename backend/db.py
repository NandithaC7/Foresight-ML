"""
db.py
=========
Plain sqlite3 storage for scan history. One table: inspections. Each row keeps
the scan's items (JSON) plus a metadata blob (model version, warnings, source
= "model" or "mock"). Uploaded images are NOT stored.
"""

import json
import sqlite3
import time
import uuid

import config


def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            items TEXT NOT NULL
        )
    """)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(inspections)")}
    if "scan_id" not in cols:
        conn.execute("ALTER TABLE inspections ADD COLUMN scan_id TEXT")
    if "meta" not in cols:
        conn.execute("ALTER TABLE inspections ADD COLUMN meta TEXT")
    conn.commit()
    conn.close()


def _row(r) -> dict:
    meta = json.loads(r["meta"]) if r["meta"] else {"source": "legacy_unknown"}
    return {"id": r["id"], "scan_id": r["scan_id"] or str(r["id"]), "ts": r["ts"],
            "items": json.loads(r["items"]), **meta}


def insert_inspection(items: list[dict], meta: dict | None = None) -> dict:
    ts = int(time.time() * 1000)
    scan_id = uuid.uuid4().hex[:12]
    # XAI overlays are large data URIs: not persisted in history.
    stored = [{k: v for k, v in it.items() if k != "xai_overlay"} for it in items]
    conn = get_conn()
    cur = conn.execute("INSERT INTO inspections (ts, items, scan_id, meta) VALUES (?, ?, ?, ?)",
                       (ts, json.dumps(stored), scan_id, json.dumps(meta or {})))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "scan_id": scan_id, "ts": ts, "items": items, **(meta or {})}


def get_inspections(limit: int | None = None) -> list[dict]:
    conn = get_conn()
    q = "SELECT * FROM inspections ORDER BY ts DESC, id DESC"
    rows = conn.execute(q + (" LIMIT ?" if limit else ""), ((limit,) if limit else ())).fetchall()
    conn.close()
    return [_row(r) for r in rows]


def get_inspection(scan_id: str) -> dict | None:
    conn = get_conn()
    r = conn.execute("SELECT * FROM inspections WHERE scan_id = ? OR CAST(id AS TEXT) = ?",
                     (scan_id, scan_id)).fetchone()
    conn.close()
    return _row(r) if r else None


def clear_inspections():
    conn = get_conn()
    conn.execute("DELETE FROM inspections")
    conn.commit()
    conn.close()


def compute_stats() -> dict:
    inspections = get_inspections()
    items = [it for insp in inspections for it in insp["items"]]
    total_items = len(items)
    discarded = len([i for i in items if i.get("tier") == "bad"])
    shelf_ready = len([i for i in items if i.get("tier") == "good"])
    return {
        "totalInspections": len(inspections),
        "totalItems": total_items,
        "discarded": discarded,
        "shelfReadyPct": round((shelf_ready / total_items) * 100) if total_items else 0,
        "avgLossPct": round((discarded / total_items) * 100) if total_items else 0,
    }
