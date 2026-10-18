"""
prepare_unet_annotation.py — build the U-Net decay-annotation batch for Label Studio.

Selects 180 sRGB images (per produce: 20 Spoiled + 10 Not_spoiled) from split v1,
keeping each image's train/val/test assignment (~60/20/20 within every stratum) and
spreading picks across capture sessions. Writes EXIF-upright copies (long side 1024 px)
to unet-annotation/images/ (derived, git-ignored), a manifest, a Label Studio task file
and the labelling config. Source files are only read.

Usage (from the repository root):
  .venv/bin/python Foresight-TR6-plus/scripts/prepare_unet_annotation.py
"""
import collections
import csv
import json
import random
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Foresight-TR6-plus/unet-annotation"
IMG = OUT / "images"
PER = {"Spoiled": 20, "Not_spoiled": 10}
SPLIT_SHARE = {"train": 0.6, "val": 0.2, "test": 0.2}
LONG_SIDE = 1024
SEED = 20261017

CONFIG = """<View>
  <Header value="Foresight U-Net annotation: draw the WHOLE fruit, then every visibly decayed area."/>
  <Header value="Decay = rot, mould, lesion, collapsed/sunken or necrotic tissue, dark bruise with a clear edge. NOT ripening colour, normal spots, stem scar, shadows, reflections."/>
  <Image name="image" value="$image" zoom="true"/>
  <PolygonLabels name="regions" toName="image" strokeWidth="2" pointSize="small" opacity="0.3">
    <Label value="fruit" background="#2F6B4F"/>
    <Label value="decay" background="#C1622E"/>
  </PolygonLabels>
  <Header value="Image decision (required)"/>
  <Choices name="decision" toName="image" choice="single" required="true">
    <Choice value="annotated_has_decay"/>
    <Choice value="annotated_no_visible_decay"/>
    <Choice value="ambiguous"/>
    <Choice value="exclude"/>
  </Choices>
  <TextArea name="notes" toName="image" placeholder="Required if ambiguous or exclude" rows="2"/>
</View>
"""


def main():
    rng = random.Random(SEED)
    rows = [r for r in csv.DictReader(open(ROOT / "artifacts/dataset/v1/split_manifest.csv")) if r["split"] in SPLIT_SHARE]
    strata = collections.defaultdict(list)
    for r in rows:
        strata[(r["produce_class"], r["source_label"])].append(r)
    picked = []
    for (produce, label), rs in sorted(strata.items()):
        n = PER[label]
        quota = {"train": round(n * 0.6), "val": round(n * 0.2)}
        quota["test"] = n - quota["train"] - quota["val"]
        for split, q in quota.items():
            by_sess = collections.defaultdict(list)
            for r in rs:
                if r["split"] == split:
                    by_sess[r["session_id"]].append(r)
            sessions = sorted(by_sess)
            rng.shuffle(sessions)
            for s in sessions:
                rng.shuffle(by_sess[s])
            got, i = [], 0
            while len(got) < q and any(by_sess[s] for s in sessions):  # round-robin over sessions
                s = sessions[i % len(sessions)]
                if by_sess[s]:
                    got.append(by_sess[s].pop())
                i += 1
            picked += got
    IMG.mkdir(parents=True, exist_ok=True)
    man, tasks = [], []
    for k, r in enumerate(sorted(picked, key=lambda r: (r["produce_class"], r["source_label"], r["split"], r["sample_id"])), 1):
        aid = f"unet_{k:03d}"
        with Image.open(ROOT / "dataset/TR-6" / r["source_relative_path"]) as im:
            im.draft("RGB", (im.width // 2, im.height // 2))
            im = ImageOps.exif_transpose(im).convert("RGB")
            s = LONG_SIDE / max(im.size)
            im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
            dst = IMG / f"{aid}.jpg"
            im.save(dst, quality=95)
            w, h = im.size
        rel = dst.relative_to(ROOT).as_posix()
        man.append({"annotation_id": aid, "sample_id": r["sample_id"], "sha256": r["sha256"], "source_relative_path": r["source_relative_path"],
                    "produce_class": r["produce_class"], "source_label": r["source_label"], "split": r["split"], "session_id": r["session_id"],
                    "image_path": rel, "width": w, "height": h, "transform": f"exif_transpose; resize long side {LONG_SIDE} (Lanczos)",
                    "annotation_status": "pending"})
        tasks.append({"data": {"image": f"/data/local-files/?d={rel}", "annotation_id": aid, "produce": r["produce_class"],
                               "dataset_label": r["source_label"], "split": r["split"]}})
    with open(OUT / "unet_annotation_manifest.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(man[0])); wr.writeheader(); wr.writerows(man)
    (OUT / "label_studio_tasks.json").write_text(json.dumps(tasks, indent=1))
    (OUT / "label_studio_config.xml").write_text(CONFIG)
    c = collections.Counter((m["produce_class"], m["source_label"], m["split"]) for m in man)
    print(len(man), "images;", dict(collections.Counter(m["split"] for m in man)), "; sessions:", len({m["session_id"] for m in man}))
    for k in sorted(c):
        print(" ", k, c[k])


if __name__ == "__main__":
    main()
