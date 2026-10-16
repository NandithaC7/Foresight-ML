"""
inference.py — loads the trained Foresight ViT checkpoint once and runs real
inference. No random or fabricated outputs: if the checkpoint is missing or
fails to load, `ModelService.ready` is False and the API returns a
model-unavailable error.

Preprocessing mirrors training (ml/data/build_cache.py + ml/common.py):
EXIF-orientation fix -> RGB -> shorter side 256 (bicubic) -> resize 224x224
-> ToTensor -> Normalize(mean, std from the pretrained backbone config).
"""
from __future__ import annotations

import base64
import io
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

import config

DISPLAY_NAMES = {"Indian_Gooseberry": "Indian Gooseberry"}
DISCLAIMER = "Visual estimate — not a food-safety guarantee."
LOW_TYPE_CONF = 0.60       # below this the produce type is flagged as uncertain
UNCERTAIN_SPOIL_BAND = 0.30  # p_spoiled in [0.30, 0.50) is shown as "uncertain"


class ImageValidationError(ValueError):
    pass


def decode_image(data: bytes) -> Image.Image:
    """Decode and sanity-check uploaded bytes. Raises ImageValidationError."""
    if not data:
        raise ImageValidationError("The uploaded file is empty.")
    Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        im = Image.open(io.BytesIO(data))
        if fmt not in ("JPEG", "PNG", "WEBP", "MPO"):
            raise ImageValidationError(f"Unsupported image format '{fmt}'. Use JPG, PNG or WEBP.")
        if im.width * im.height > config.MAX_IMAGE_PIXELS:
            raise ImageValidationError("Image dimensions are too large.")
        if min(im.width, im.height) < config.MIN_IMAGE_SIDE:
            raise ImageValidationError(f"Image is too small (minimum {config.MIN_IMAGE_SIDE}px per side).")
        if fmt in ("JPEG", "MPO"):
            im.draft("RGB", (max(1, im.width // 8), max(1, im.height // 8)))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.load()
        return im
    except ImageValidationError:
        raise
    except Image.DecompressionBombError:
        raise ImageValidationError("Image dimensions are too large.")
    except Exception:
        raise ImageValidationError("The file could not be decoded as an image (corrupt or not an image).")


def shorter_side_256(im: Image.Image) -> Image.Image:
    s = 256 / min(im.size)
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)


@dataclass
class ModelService:
    path: Path
    ready: bool = False
    error: str | None = None
    info: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def load(self) -> None:
        if not self.path.exists():
            self.ready, self.error = False, (
                f"Checkpoint not found at {self.path}. Train the model (ml/train/train_vit.py) and copy "
                "artifacts/runs/<run>/best.pt there, or set FORESIGHT_MODEL_PATH.")
            return
        try:
            import timm
            import torch
            import torch.nn as nn
            from torchvision import transforms as T

            ck = torch.load(self.path, map_location="cpu", weights_only=False)
            cfg = ck["config"]

            class ForesightViT(nn.Module):  # same parameter layout as ml/common.py
                def __init__(self):
                    super().__init__()
                    self.backbone = timm.create_model(cfg["backbone"], pretrained=False, num_classes=0)
                    d = self.backbone.num_features
                    self.drop = nn.Dropout(0.1)
                    self.head_type = nn.Linear(d, len(cfg["produce_classes"]))
                    self.head_spoil = nn.Linear(d, len(cfg["spoilage_classes"]))

                def forward(self, x):
                    z = self.drop(self.backbone(x))
                    return self.head_type(z), self.head_spoil(z)

            dev = config.DEVICE
            if dev == "auto":
                dev = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
            model = ForesightViT()
            model.load_state_dict(ck["state_dict"])
            self.model = model.to(dev).eval()
            self.device = dev
            self.torch = torch
            self.cfg = cfg
            self.tf = T.Compose([T.Resize((cfg["img_size"], cfg["img_size"])), T.ToTensor(),
                                 T.Normalize(cfg["mean"], cfg["std"])])
            self.info = {
                "name": "foresight-vit",
                "version": f"{cfg['run_id']}@epoch{ck.get('epoch')}",
                "backbone": cfg["backbone"],
                "checkpoint": str(self.path.name),
                "produce_classes": cfg["produce_classes"],
                "spoilage_classes": cfg["spoilage_classes"],
                "img_size": cfg["img_size"],
                "device": dev,
                "trained_at": cfg.get("finished_at"),
                "val_composite_macro_f1": cfg.get("best_val_composite_macro_f1"),
            }
            self.ready, self.error = True, None
        except Exception as e:  # pragma: no cover - surfaced through /health
            self.ready, self.error = False, f"Failed to load checkpoint: {type(e).__name__}: {e}"

    # ------------------------------------------------------------------
    def _rollout(self, x) -> np.ndarray:
        """Attention rollout (Abnar & Zuidema, 2020): average heads, add identity,
        renormalise, multiply across layers; CLS-to-patch row -> 14x14 map."""
        torch = self.torch
        blocks = self.model.backbone.blocks
        attns, hooks = [], []
        for b in blocks:
            b.attn.fused_attn = False
            hooks.append(b.attn.attn_drop.register_forward_hook(lambda m, i, o: attns.append(o.detach())))
        try:
            with torch.no_grad():
                out = self.model(x)
        finally:
            for h in hooks:
                h.remove()
            for b in blocks:
                b.attn.fused_attn = True
        n_tok = attns[0].shape[-1]
        r = torch.eye(n_tok, device=attns[0].device)
        for a in attns:
            a = a[0].mean(0)
            a = a + torch.eye(n_tok, device=a.device)
            a = a / a.sum(-1, keepdim=True)
            r = a @ r
        n_prefix = getattr(self.model.backbone, "num_prefix_tokens", 1)
        m = r[0, n_prefix:].cpu().numpy()
        g = int(round(m.size ** 0.5))
        m = m.reshape(g, g)
        m = (m - m.min()) / (m.max() - m.min() + 1e-8)
        return m, out

    @staticmethod
    def _overlay_png(img224: Image.Image, heat: np.ndarray) -> str:
        h = np.asarray(Image.fromarray((heat * 255).astype(np.uint8)).resize(img224.size, Image.BILINEAR),
                       dtype=np.float32) / 255.0
        color = np.stack([np.clip(1.5 * h, 0, 1), np.clip(1.5 * h - 0.5, 0, 1), np.zeros_like(h)], -1)  # dark->red->yellow
        base = np.asarray(img224, dtype=np.float32) / 255.0
        out = (0.55 * base + 0.45 * color) * 255
        buf = io.BytesIO()
        Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def predict(self, im: Image.Image, xai: bool = False) -> dict:
        if not self.ready:
            raise RuntimeError(self.error or "model unavailable")
        torch = self.torch
        im256 = shorter_side_256(im)
        x = self.tf(im256).unsqueeze(0).to(self.device)
        t0 = time.perf_counter()
        with self._lock:
            if xai:
                heat, (lt, ls) = self._rollout(x)
            else:
                with torch.no_grad():
                    lt, ls = self.model(x)
            pt = lt.softmax(1)[0].float().cpu().numpy()
            ps = ls.softmax(1)[0].float().cpu().numpy()
        ms = (time.perf_counter() - t0) * 1000
        res = {"p_type": pt, "p_spoil": ps, "inference_ms": ms}
        if xai:
            res["xai_overlay"] = self._overlay_png(im256.resize((self.cfg["img_size"],) * 2, Image.BILINEAR), heat)
        return res


def compose_item(pred: dict, classes: list[str], xai: bool) -> tuple[dict, list[str]]:
    """Deterministic mapping from model outputs to the UI item contract."""
    pt, ps = pred["p_type"], pred["p_spoil"]
    ti = int(pt.argmax())
    produce = classes[ti]
    type_conf = float(pt[ti])
    p_spoiled = float(ps[1])
    spoiled = p_spoiled >= 0.5
    warnings = []
    if type_conf < LOW_TYPE_CONF:
        warnings.append(
            f"Low confidence on produce type ({type_conf:.0%}). The photo may not show one of the six supported "
            "items (Banana, Carrot, Guava, Indian Gooseberry, Mango, Tomato); treat this result as unreliable.")
    if spoiled:
        tier = "bad"
        action = "Visible spoilage cues detected — inspect closely and discard if decay is confirmed."
    elif p_spoiled >= UNCERTAIN_SPOIL_BAND or type_conf < LOW_TYPE_CONF:
        tier = "warn"
        action = "Model is uncertain — inspect the item manually before using it."
    else:
        tier = "good"
        action = "No visible spoilage cues detected. Still check smell and texture before eating."
    item = {
        "name": DISPLAY_NAMES.get(produce, produce),
        "produce_class": produce,
        "produce_confidence": round(type_conf, 4),
        "produce_probabilities": {c: round(float(p), 4) for c, p in zip(classes, pt)},
        "spoilage_label": "Spoiled" if spoiled else "Not spoiled",
        "spoilage_confidence": round(p_spoiled if spoiled else 1 - p_spoiled, 4),
        "p_spoiled": round(p_spoiled, 4),
        # `freshness` keeps the existing UI key: it is the model's Not_spoiled softmax score x 100,
        # NOT a calibrated freshness percentage.
        "freshness": int(round((1 - p_spoiled) * 100)),
        "tier": tier,
        "days": None,
        "shelf_life_status": "unavailable",
        "decayPct": None,
        "decay_mask_available": False,
        "segmentation_status": "annotation_pending",
        "action": action,
        "xai_overlay": pred.get("xai_overlay") if xai else None,
        "xai_method": "attention_rollout" if xai else None,
    }
    return item, warnings


service = ModelService(config.MODEL_PATH)
