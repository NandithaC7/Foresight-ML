"""Tests against the REAL trained checkpoint (skipped if it has not been installed).

These check real inference on genuine TR-6 test-split source images (full
resolution, through the same decode/EXIF/resize path the API uses), and that
the backend preprocessing matches the training-time cache preprocessing.
"""
import csv
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conftest import REAL_CKPT, make_client

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "artifacts/dataset/v1/split_manifest.csv"
DATASET = ROOT / "dataset/TR-6"
pytestmark = pytest.mark.skipif(not REAL_CKPT.exists(), reason="real checkpoint not installed")


def held_out_rows(per_stratum=1):
    rows = [r for r in csv.DictReader(MANIFEST.open()) if r["split"] == "test"]
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["sample_id"]):
        k = (r["produce_class"], r["source_label"])
        if k not in seen and (DATASET / r["source_relative_path"]).exists():
            seen.add(k); out.append(r)
    return out


@pytest.fixture(scope="module")
def real_client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    probe = REAL_CKPT.parent / "visible_decay_probe.json"
    with make_client(mp, tmp_path_factory.mktemp("real"), REAL_CKPT, probe=probe if probe.exists() else None,
                     unet=(REAL_CKPT.parent / "unet_pilot.pt") if (REAL_CKPT.parent / "unet_pilot.pt").exists() else None,
                     shelf=(REAL_CKPT.parent / "shelf_life_proxy.json") if (REAL_CKPT.parent / "shelf_life_proxy.json").exists() else None) as c:
        yield c
    mp.undo()


def test_real_model_loads(real_client):
    h = real_client.get("/health").json()
    assert h["model_loaded"] is True and h["mock_mode"] is False
    assert not h["model_version"].startswith("tiny")


def test_real_inference_on_held_out_source_images(real_client):
    rows = held_out_rows()
    assert len(rows) == 12
    correct_type, correct_spoil = 0, 0
    for r in rows:
        data = (DATASET / r["source_relative_path"]).read_bytes()  # original 4000x3000 JPEG, read-only
        res = real_client.post("/api/analyze", files={"photo": ("x.jpg", data, "image/jpeg")})
        assert res.status_code == 200, res.text
        it = res.json()["items"][0]
        correct_type += it["produce_class"] == r["produce_class"]
        correct_spoil += (it["spoilage_label"] == "Spoiled") == (r["source_label"] == "Spoiled")
    # produce type is near-perfect on held-out data; require at least 11/12
    assert correct_type >= 11, correct_type
    assert correct_spoil >= 9, correct_spoil


def test_backend_preprocessing_matches_training_cache():
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    import inference
    r = held_out_rows()[0]
    api_img = inference.shorter_side_256(inference.decode_image((DATASET / r["source_relative_path"]).read_bytes()))
    cache_img = Image.open(ROOT / "artifacts/cache/srgb_256" / f"{r['sha256']}.jpg").convert("RGB")
    assert api_img.size == cache_img.size
    diff = np.abs(np.asarray(api_img, dtype=np.float32) - np.asarray(cache_img, dtype=np.float32)).mean()
    assert diff < 3.0, diff  # only JPEG re-encoding differences remain


def test_png_upload_of_real_image(real_client):
    r = held_out_rows()[0]
    im = Image.open(DATASET / r["source_relative_path"]); im.draft("RGB", (500, 375))
    buf = io.BytesIO(); im.convert("RGB").save(buf, "PNG")
    res = real_client.post("/api/analyze", files={"photo": ("x.png", buf.getvalue(), "image/png")}, params={"xai": "true"})
    assert res.status_code == 200
    assert res.json()["items"][0]["xai_overlay"].startswith("data:image/png")


def test_visible_decay_probe_served(real_client):
    models = {m["id"]: m for m in real_client.get("/api/models").json()["models"]}
    assert models["visible_decay"]["status"] == "loaded"
    r = held_out_rows()[0]
    it = real_client.post("/api/analyze", files={"photo": ("x.jpg", (DATASET / r["source_relative_path"]).read_bytes(), "image/jpeg")}).json()["items"][0]
    assert it["visible_decay_status"] == "model" and 0 <= it["visible_decay_probability"] <= 1
    assert it["visible_decay_label"] in ("Visible decay", "No visible decay")


def test_unet_segmentation_when_trained(real_client):
    models = {m["id"]: m for m in real_client.get("/api/models").json()["models"]}
    if models["unet"]["status"] != "loaded":
        pytest.skip("no trained U-Net checkpoint")
    r = held_out_rows()[0]
    it = real_client.post("/api/analyze", files={"photo": ("x.jpg", (DATASET / r["source_relative_path"]).read_bytes(), "image/jpeg")}).json()["items"][0]
    assert it["decay_mask_available"] is True and it["segmentation_status"] == "pilot_model"
    assert it["decay_mask_overlay"].startswith("data:image/png") and (it["decayPct"] is None or 0 <= it["decayPct"] <= 100)


def test_shelf_life_proxy_served(real_client):
    models = {m["id"]: m for m in real_client.get("/api/models").json()["models"]}
    if models["shelf_life"]["status"] != "loaded":
        pytest.skip("no shelf-life proxy model")
    r = held_out_rows()[0]
    it = real_client.post("/api/analyze", files={"photo": ("x.jpg", (DATASET / r["source_relative_path"]).read_bytes(), "image/jpeg")}).json()["items"][0]
    assert it["shelf_life_status"] == "proxy_target" and isinstance(it["days"], int) and it["days"] >= 0
