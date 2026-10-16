"""Data-integrity and model unit tests for the ML pipeline."""
import collections
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from common import PRODUCE_CLASSES, SPOILAGE_CLASSES, corrupt  # noqa: E402

V1 = ROOT / "artifacts/dataset/v1"
ROWS = list(csv.DictReader((V1 / "split_manifest.csv").open()))
ELIG = [r for r in ROWS if r["split"] in ("train", "val", "test")]
REQUIRED = ["sample_id", "source_relative_path", "source_dataset", "sha256", "content_group_id", "produce_class",
            "source_label", "label_status", "modality", "annotation_status", "mask_path", "bbox_path", "specimen_id",
            "session_id", "split", "derived_from", "transformation", "parameters", "seed", "notes", "exclusion_reason"]


def test_manifest_schema():
    assert set(REQUIRED) <= set(ROWS[0].keys())
    assert len({r["sha256"] for r in ROWS}) == len(ROWS)  # one row per unique content


def test_eligible_rows_have_valid_labels():
    assert all(r["produce_class"] in PRODUCE_CLASSES and r["source_label"] in SPOILAGE_CLASSES for r in ELIG)
    assert all(r["modality"] == "srgb" and r["exclusion_reason"] == "" for r in ELIG)
    assert all(r["specimen_id"] == "" for r in ROWS)  # never invented


def test_conflicting_labels_excluded():
    conf = [r for r in ROWS if r["label_status"] == "inherited_conflicting"]
    assert len(conf) == 170 and all(r["split"] == "excluded" for r in conf)


def test_no_leakage_between_splits():
    by_hash, by_session = collections.defaultdict(set), collections.defaultdict(set)
    for r in ELIG:
        for p in r["all_source_paths"].split(";"):
            by_hash[p].add(r["split"])
        by_session[r["session_id"]].add(r["split"])
    assert all(len(v) == 1 for v in by_hash.values())
    assert all(len(v) == 1 for v in by_session.values())


def test_split_fractions_close_to_60_20_20():
    n = collections.Counter(r["split"] for r in ELIG)
    tot = sum(n.values())
    assert abs(n["train"] / tot - 0.6) < 0.02 and abs(n["val"] / tot - 0.2) < 0.02 and abs(n["test"] / tot - 0.2) < 0.02
    s = json.loads((V1 / "split_summary.json").read_text())
    assert s["split_counts"] == {"train": n["train"], "val": n["val"], "test": n["test"]}


def test_every_stratum_in_every_split():
    seen = {(r["produce_class"], r["source_label"], r["split"]) for r in ELIG}
    for p in PRODUCE_CLASSES:
        for l in SPOILAGE_CLASSES:
            for sp in ("train", "val", "test"):
                assert (p, l, sp) in seen, (p, l, sp)


@pytest.mark.skipif(not (ROOT / "dataset/TR-6").exists(), reason="dataset not present")
def test_source_files_unchanged():
    """Re-hash a deterministic sample of originals and compare with the audit hashes."""
    sample = sorted(ELIG, key=lambda r: r["sha256"])[::400]
    for r in sample:
        assert hashlib.sha256((ROOT / "dataset/TR-6" / r["source_relative_path"]).read_bytes()).hexdigest() == r["sha256"]


def test_corruptions_are_deterministic_and_bounded():
    img = Image.new("RGB", (256, 300), (120, 200, 60))
    for kind, lvl in (("gaussian", 0.1), ("salt_pepper", 0.05), ("speckle", 0.2)):
        a, b = np.asarray(corrupt(img, kind, lvl, 7)), np.asarray(corrupt(img, kind, lvl, 7))
        assert a.shape == (224, 224, 3) and (a == b).all()
        assert not (a == np.asarray(corrupt(img, kind, lvl, 8))).all()
    sp = np.asarray(corrupt(img, "salt_pepper", 0.1, 1))
    frac = ((sp == 0).all(-1) | (sp == 255).all(-1)).mean()
    assert 0.07 < frac < 0.13


def test_model_forward_shapes():
    import torch
    from common import ForesightViT
    m = ForesightViT("vit_tiny_patch16_224", pretrained=False).eval()
    with torch.no_grad():
        lt, ls, z = m(torch.randn(2, 3, 224, 224), return_features=True)
    assert lt.shape == (2, 6) and ls.shape == (2, 2) and z.shape[0] == 2


def test_gan_outputs_marked_synthetic_and_train_only():
    man = ROOT / "artifacts/experiments/gan/generated_manifest.csv"
    if not man.exists():
        pytest.skip("GAN not generated")
    rows = list(csv.DictReader(man.open()))
    assert rows and all(r["provenance"] == "synthetic_cdcgan_train_only" for r in rows)
    assert all("/experiments/gan/generated/" in r["path"] for r in rows)
