"""
db.py
=========
Plain sqlite3 (Python standard library — no extra install needed beyond
what's already in requirements.txt). One table: inspections, storing each
scan's items as a JSON blob. Simple by design — this is enough for a
course-project demo; swap for Postgres later only if you need multi-instance
scaling.
"""

import sqlite3
import json
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "foresight.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            items TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def insert_inspection(items: list[dict]) -> dict:
    ts = int(time.time() * 1000)
    conn = get_conn()
    cur = conn.execute("INSERT INTO inspections (ts, items) VALUES (?, ?)", (ts, json.dumps(items)))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "ts": ts, "items": items}


def get_inspections() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM inspections ORDER BY ts DESC").fetchall()
    conn.close()
    return [{"id": r["id"], "ts": r["ts"], "items": json.loads(r["items"])} for r in rows]


def clear_inspections():
    conn = get_conn()
    conn.execute("DELETE FROM inspections")
    conn.commit()
    conn.close()


def compute_stats() -> dict:
    inspections = get_inspections()
    items = [it for insp in inspections for it in insp["items"]]
    total_items = len(items)
    discarded = len([i for i in items if i["tier"] == "bad"])
    shelf_ready = len([i for i in items if i["tier"] == "good"])
    return {
        "totalInspections": len(inspections),
        "totalItems": total_items,
        "discarded": discarded,
        "shelfReadyPct": round((shelf_ready / total_items) * 100) if total_items else 0,
        "avgLossPct": round((discarded / total_items) * 100) if total_items else 0,
    }
