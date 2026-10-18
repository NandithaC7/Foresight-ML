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
import json
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

    runtime: str = "torch"

    def _feat_dim(self) -> int:
        return self.cfg["feature_dim"] if self.runtime == "onnx" else self.model.backbone.num_features

    def _load_onnx(self) -> None:
        """PyTorch-free path: int8 ViT + U-Net in ONNX Runtime (for small hosts)."""
        import onnxruntime as ort
        p, mp = config.ONNX_VIT_PATH, config.ONNX_VIT_META_PATH
        if not (p.exists() and mp.exists()):
            self.ready, self.error = False, f"ONNX model not found at {p.name} (run deploy/export_onnx.py or set FORESIGHT_MODEL_REPO)."
            return
        try:
            so = ort.SessionOptions(); so.intra_op_num_threads = 2
            so.enable_cpu_mem_arena = False  # keep peak RAM low on 512 MB hosts
            so.enable_mem_pattern = False
            self.sess = ort.InferenceSession(str(p), so, providers=["CPUExecutionProvider"])
            cfg = json.loads(mp.read_text())
            self.runtime, self.cfg, self.device = "onnx", cfg, "cpu"
            self.info = {"name": "foresight-vit", "version": f"{cfg['run_id']}@epoch{cfg['epoch']} (int8 ONNX)", "backbone": cfg["backbone"],
                         "checkpoint": p.name, "produce_classes": cfg["produce_classes"], "spoilage_classes": cfg["spoilage_classes"],
                         "img_size": cfg["img_size"], "device": "cpu (onnxruntime int8)", "trained_at": cfg.get("finished_at"),
                         "val_composite_macro_f1": cfg.get("best_val_composite_macro_f1")}
            self.ready, self.error = True, None
            self._load_probe(cfg)
            self._load_shelf_life(cfg)
            self.unet, self.unet_info, self.unet_error = None, {}, None
            if config.ONNX_UNET_PATH.exists() and config.ONNX_UNET_META_PATH.exists():
                self.unet = ort.InferenceSession(str(config.ONNX_UNET_PATH), so, providers=["CPUExecutionProvider"])
                self.unet_cfg = json.loads(config.ONNX_UNET_META_PATH.read_text())
                src = "machine-generated" if self.unet_cfg.get("mask_source") == "auto" else "human-drawn"
                self.unet_info = {"version": f"unet_pilot ({self.unet_cfg['n_train_masks']} {src} training masks, ONNX)", "status_note": self.unet_cfg.get("status"),
                                  "mask_source": src, "eval_mean": self.unet_cfg.get("eval_mean"), "n_eval": self.unet_cfg.get("n_eval")}
            else:
                self.unet_error = "No ONNX U-Net file."
        except Exception as e:  # pragma: no cover
            self.ready, self.error = False, f"Failed to load ONNX model: {type(e).__name__}: {e}"

    def _predict_onnx(self, im: Image.Image, xai: bool) -> dict:
        cfg = self.cfg
        im256 = shorter_side_256(im)
        size = cfg["img_size"]
        a = (np.asarray(im256.resize((size, size), Image.BILINEAR), np.float32) / 255 - np.asarray(cfg["mean"], np.float32)) / np.asarray(cfg["std"], np.float32)
        t0 = time.perf_counter()
        with self._lock:
            lt, ls, z, attn = self.sess.run(None, {"image": a.transpose(2, 0, 1)[None]})
            sm = lambda v: (lambda e: e / e.sum())(np.exp(v - v.max()))  # noqa: E731
            pt, ps, zz = sm(lt[0]), sm(ls[0]), z[0]
            pv, sd = self._visible_decay(zz), self._shelf_days(zz)
            seg = self._segment(im256)
        res = {"p_type": pt, "p_spoil": ps, "p_visible_decay": pv, "shelf_days": sd, "segmentation": seg,
               "inference_ms": (time.perf_counter() - t0) * 1000}
        if xai:
            n = attn.shape[-1]; r = np.eye(n, dtype=np.float32)
            for blk in attn:
                b = blk + np.eye(n, dtype=np.float32); r = (b / b.sum(-1, keepdims=True)) @ r
            m = r[0, 1:]; g = int(round(m.size ** 0.5)); m = m.reshape(g, g)
            m = (m - m.min()) / (m.max() - m.min() + 1e-8)
            res["xai_overlay"] = self._overlay_png(im256.resize((size, size), Image.BILINEAR), m)
        return res

    def load(self) -> None:
        if config.RUNTIME == "onnx":
            return self._load_onnx()
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
                    z = self.backbone(x)  # CLS embedding (dropout is identity in eval)
                    return self.head_type(z), self.head_spoil(z), z

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
            self._load_probe(cfg)
            self._load_unet()
            self._load_shelf_life(cfg)
        except Exception as e:  # pragma: no cover - surfaced through /health
            self.ready, self.error = False, f"Failed to load checkpoint: {type(e).__name__}: {e}"

    def _load_probe(self, cfg) -> None:
        """Optional visible-decay probe: logistic regression on the CLS embedding, trained on
        human image-level labels. Only used if it was fitted on this exact backbone checkpoint."""
        self.probe, self.probe_error = None, None
        p = config.VISIBLE_DECAY_PROBE_PATH
        if not p.exists():
            self.probe_error = f"Probe file not found at {p.name}."
            return
        pr = json.loads(p.read_text())
        dim = self._feat_dim()
        if pr.get("backbone_checkpoint") != cfg.get("run_id") or len(pr["coef"]) != dim:
            self.probe_error = "Probe was trained on a different backbone checkpoint; disabled."
            return
        self.probe = {k: np.asarray(pr[k], dtype=np.float32) for k in ("mean", "scale", "coef")}
        self.probe.update(intercept=float(pr["intercept"]), threshold=float(pr["threshold"]))
        self.probe_info = {k: pr[k] for k in ("name", "version", "trained_on", "test_metrics")}

    def _load_shelf_life(self, cfg) -> None:
        """Optional PROXY shelf-life regressor (days until the TR-6 'Spoiled' label)."""
        self.shelf, self.shelf_info, self.shelf_error = None, {}, None
        p = config.SHELF_LIFE_PROXY_PATH
        if not p.exists():
            self.shelf_error = "No shelf-life proxy model file."
            return
        pr = json.loads(p.read_text())
        if pr.get("backbone_checkpoint") != cfg.get("run_id") or len(pr["coef"]) != self._feat_dim():
            self.shelf_error = "Shelf-life proxy was fitted on a different backbone; disabled."
            return
        self.shelf = {k: np.asarray(pr[k], np.float32) for k in ("mean", "scale", "coef")} | {"intercept": float(pr["intercept"]), "clip": pr["clip"]}
        self.shelf_info = {"version": pr["version"], "target": pr["target"], "test_metrics": pr["test_metrics"]}

    def _shelf_days(self, z) -> float | None:
        if not getattr(self, "shelf", None):
            return None
        f = (z.astype(np.float32) - self.shelf["mean"]) / self.shelf["scale"]
        return float(np.clip(f @ self.shelf["coef"] + self.shelf["intercept"], *self.shelf["clip"]))

    def _load_unet(self) -> None:
        """Optional PILOT U-Net (fruit + decay masks) trained on human polygons."""
        self.unet, self.unet_info, self.unet_error = None, {}, None
        p = config.UNET_PATH
        if not p.exists():
            self.unet_error = "No trained U-Net checkpoint (needs human-drawn decay polygons)."
            return
        try:
            from unet_model import UNetResNet18
            ck = self.torch.load(p, map_location="cpu", weights_only=False)
            net = UNetResNet18(pretrained=False)
            net.load_state_dict(ck["state_dict"])
            self.unet = net.to(self.device).eval()
            self.unet_cfg = ck
            src = "machine-generated" if ck.get("mask_source") == "auto" else "human-drawn"
            self.unet_info = {"version": f"unet_pilot ({ck['n_train_masks']} {src} training masks)", "status_note": ck.get("status"), "mask_source": src,
                              "eval_mean": ck.get("eval_mean"), "n_eval": ck.get("n_eval")}
        except Exception as e:  # pragma: no cover
            self.unet, self.unet_error = None, f"Failed to load U-Net: {type(e).__name__}: {e}"

    def _segment(self, im256: Image.Image) -> dict | None:
        if not getattr(self, "unet", None):
            return None
        size = self.unet_cfg["size"]
        img = im256.resize((size, size), Image.BILINEAR)
        a = (np.asarray(img, np.float32) / 255 - np.asarray(self.unet_cfg["mean"], np.float32)) / np.asarray(self.unet_cfg["std"], np.float32)
        if self.runtime == "onnx":
            pr = self.unet.run(None, {"image": a.transpose(2, 0, 1)[None].astype(np.float32)})[0][0] > 0  # logit > 0 <=> sigmoid > 0.5
        else:
            torch = self.torch
            x = torch.from_numpy(a).permute(2, 0, 1)[None].to(self.device)
            with torch.no_grad():
                pr = torch.sigmoid(self.unet(x))[0].cpu().numpy() > 0.5
        fruit, decay = pr[0], pr[1] & pr[0]
        cov = float(decay.sum() / fruit.sum() * 100) if fruit.sum() > 0 else None
        base = np.asarray(img, np.float32) / 255
        o = base.copy()
        o[fruit] = 0.65 * o[fruit] + 0.35 * np.array([0.18, 0.42, 0.31])
        o[decay] = 0.4 * o[decay] + 0.6 * np.array([0.9, 0.3, 0.1])
        buf = io.BytesIO(); Image.fromarray((o * 255).clip(0, 255).astype(np.uint8)).save(buf, "PNG")
        return {"decay_coverage_pct": None if cov is None else round(cov, 1),
                "mask_overlay": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}

    def _visible_decay(self, z) -> float | None:
        if not getattr(self, "probe", None):
            return None
        f = (z.astype(np.float32) - self.probe["mean"]) / self.probe["scale"]
        return float(1 / (1 + np.exp(-(f @ self.probe["coef"] + self.probe["intercept"]))))

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
        if self.runtime == "onnx":
            return self._predict_onnx(im, xai)
        torch = self.torch
        im256 = shorter_side_256(im)
        x = self.tf(im256).unsqueeze(0).to(self.device)
        t0 = time.perf_counter()
        with self._lock:
            if xai:
                heat, (lt, ls, z) = self._rollout(x)
            else:
                with torch.no_grad():
                    lt, ls, z = self.model(x)
            pt = lt.softmax(1)[0].float().cpu().numpy()
            ps = ls.softmax(1)[0].float().cpu().numpy()
            zz = z[0].float().cpu().numpy()
            pv = self._visible_decay(zz)
            sd = self._shelf_days(zz)
            seg = self._segment(im256)
        ms = (time.perf_counter() - t0) * 1000
        res = {"p_type": pt, "p_spoil": ps, "p_visible_decay": pv, "shelf_days": sd, "segmentation": seg, "inference_ms": ms}
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
    pv = pred.get("p_visible_decay")
    if pv is not None and spoiled != (pv >= 0.5):
        warnings.append("The spoilage model and the visible-decay check disagree: "
                        + ("spoilage cues without clearly visible decay (possibly an early stage)." if spoiled
                           else "visible decay-like marks but no overall spoilage prediction. Inspect manually."))
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
        "days": None if pred.get("shelf_days") is None else int(round(pred["shelf_days"])),
        "shelf_life_days_estimate": None if pred.get("shelf_days") is None else round(pred["shelf_days"], 1),
        "shelf_life_status": "proxy_target" if pred.get("shelf_days") is not None else "unavailable",
        "decayPct": (pred.get("segmentation") or {}).get("decay_coverage_pct"),
        "decay_mask_available": bool(pred.get("segmentation")),
        "segmentation_status": "pilot_model" if pred.get("segmentation") else "annotation_pending",
        "decay_mask_overlay": (pred.get("segmentation") or {}).get("mask_overlay"),
        "action": action,
        "visible_decay_probability": None if pv is None else round(pv, 4),
        "visible_decay_label": None if pv is None else ("Visible decay" if pv >= 0.5 else "No visible decay"),
        "visible_decay_status": "model" if pv is not None else "unavailable",
        "xai_overlay": pred.get("xai_overlay") if xai else None,
        "xai_method": "attention_rollout" if xai else None,
    }
    return item, warnings


service = ModelService(config.MODEL_PATH)
