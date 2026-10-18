"""
export_visible_decay_labels.py — export the human image-level decisions from the
local Label Studio project "Foresight U-Net decay" (read-only) and join them with
the annotation manifest (produce, dataset label, split, session, sha256).

Output: unet-annotation/human_visible_decay_labels.csv
  decision            : annotated_has_decay | annotated_no_visible_decay | ambiguous | exclude
  visible_decay       : 1 / 0 for the two definite decisions, empty otherwise
  annotator_id, lead_time_s, created_at, notes
No polygons existed at export time (0 fruit / 0 decay shapes), so no masks are produced.

Usage: python3 Foresight-TR6-plus/scripts/export_visible_decay_labels.py
"""
import csv
import json
import sqlite3
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
DB = WS / ".labelstudio-data/label_studio.sqlite3"
OUT = WS / "unet-annotation/human_visible_decay_labels.csv"


def main():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    pid = db.execute("select id from project where title = 'Foresight U-Net decay'").fetchone()[0]
    man = {r["annotation_id"]: r for r in csv.DictReader(open(WS / "unet-annotation/unet_annotation_manifest.csv"))}
    rows, polygons = [], 0
    q = ("select t.data, c.result, c.completed_by_id, c.lead_time, c.created_at, c.was_cancelled "
         "from task t join task_completion c on c.task_id = t.id where t.project_id = ? order by t.id")
    for data, res, uid, lt, ca, cancelled in db.execute(q, (pid,)):
        if cancelled:
            continue
        img = list(json.loads(data).values())[0].split("/")[-1]
        aid = img.rsplit(".", 1)[0]
        decision, notes = None, []
        for it in json.loads(res):
            if it["type"] == "choices":
                decision = it["value"]["choices"][0]
            elif it["type"] == "textarea":
                notes += it["value"]["text"]
            elif it["type"] == "polygonlabels":
                polygons += 1
        m = man[aid]
        rows.append({**{k: m[k] for k in ("annotation_id", "sample_id", "sha256", "source_relative_path", "produce_class",
                                          "source_label", "split", "session_id")},
                     "decision": decision,
                     "visible_decay": {"annotated_has_decay": 1, "annotated_no_visible_decay": 0}.get(decision, ""),
                     "annotator_id": uid, "lead_time_s": round(lt or 0, 1), "created_at": ca, "notes": " | ".join(notes)})
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} annotations exported to {OUT.relative_to(WS.parent)}; polygons found: {polygons}")


if __name__ == "__main__":
    main()
