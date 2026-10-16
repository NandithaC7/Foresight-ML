import io
import sys
from pathlib import Path

import pytest
from PIL import Image

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import config  # noqa: E402
import inference  # noqa: E402

REAL_CKPT = BACKEND / "models" / "foresight_vit.pt"


@pytest.fixture(scope="session")
def tiny_ckpt(tmp_path_factory):
    """A tiny, randomly initialised checkpoint with the production layout.
    Used only to exercise API/loading code paths — never for metrics."""
    import timm
    import torch
    import torch.nn as nn

    backbone = "vit_tiny_patch16_224"
    cfg = {"run_id": "tiny_test_fixture", "backbone": backbone, "img_size": 224,
           "mean": [0.5, 0.5, 0.5], "std": [0.5, 0.5, 0.5],
           "produce_classes": ["Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato"],
           "spoilage_classes": ["Not_spoiled", "Spoiled"]}

    class M(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = timm.create_model(backbone, pretrained=False, num_classes=0)
            self.drop = nn.Dropout(0.1)
            self.head_type = nn.Linear(self.backbone.num_features, 6)
            self.head_spoil = nn.Linear(self.backbone.num_features, 2)

    p = tmp_path_factory.mktemp("ckpt") / "tiny.pt"
    torch.save({"state_dict": M().state_dict(), "config": cfg, "epoch": 0}, p)
    return p


def make_client(monkeypatch, tmp_path, ckpt_path, mock=False, max_mb=None):
    from fastapi.testclient import TestClient

    import main

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "MOCK_MODE", mock)
    monkeypatch.setattr(config, "DEVICE", "cpu")
    monkeypatch.setattr(config, "MODEL_METRICS_PATH", tmp_path / "none.json")
    if max_mb is not None:
        monkeypatch.setattr(config, "MAX_UPLOAD_MB", max_mb)
    monkeypatch.setattr(inference, "service", inference.ModelService(Path(ckpt_path)))
    return TestClient(main.app)


@pytest.fixture
def client(monkeypatch, tmp_path, tiny_ckpt):
    with make_client(monkeypatch, tmp_path, tiny_ckpt) as c:
        yield c


def image_bytes(fmt="JPEG", size=(320, 240), color=(200, 120, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()
