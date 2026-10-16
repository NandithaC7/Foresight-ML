"""Shared pieces for Foresight training/evaluation: model, dataset, transforms,
corruptions and metrics. Kept free of backend imports."""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms as T

PRODUCE_CLASSES = ["Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato"]
SPOILAGE_CLASSES = ["Not_spoiled", "Spoiled"]
IMG_SIZE = 224


def pick_device(pref: str = "auto") -> torch.device:
    if pref != "auto":
        return torch.device(pref)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


class ForesightViT(nn.Module):
    """Pretrained ViT backbone (timm) + two linear heads.

    z = ViT(x) (CLS-token embedding)
    p_type     = softmax(W_type z + b_type)        6 produce classes
    p_spoilage = softmax(W_sp z + b_sp)            Not_spoiled / Spoiled
    No shelf-life head: TR-6 has no measured time-to-endpoint labels.
    """

    def __init__(self, backbone: str, pretrained: bool = True, drop: float = 0.1):
        super().__init__()
        import timm

        self.backbone = timm.create_model(backbone, pretrained=pretrained, num_classes=0)
        d = self.backbone.num_features
        self.drop = nn.Dropout(drop)
        self.head_type = nn.Linear(d, len(PRODUCE_CLASSES))
        self.head_spoil = nn.Linear(d, len(SPOILAGE_CLASSES))

    def forward(self, x, return_features: bool = False):
        z = self.backbone(x)
        zt = self.drop(z)
        out = (self.head_type(zt), self.head_spoil(zt))
        return (*out, z) if return_features else out


def norm_stats(backbone: str) -> tuple[list[float], list[float]]:
    # ImageNet-21k augreg ViTs use 0.5/0.5; others use ImageNet stats. Taken from the
    # pretrained checkpoint's config, never fitted on TR-6 data.
    import timm

    cfg = timm.create_model(backbone, pretrained=False).pretrained_cfg
    return list(cfg.get("mean", (0.485, 0.456, 0.406))), list(cfg.get("std", (0.229, 0.224, 0.225)))


def build_transforms(mean, std, train: bool, aug: str = "conventional"):
    if train and aug == "conventional":
        return T.Compose([
            T.Resize((IMG_SIZE + 16, IMG_SIZE + 16)),
            T.RandomCrop(IMG_SIZE),
            T.RandomHorizontalFlip(),
            T.RandomVerticalFlip(),
            T.RandomRotation(15),
            # Brightness/contrast only: hue/saturation shifts could erase colour-based spoilage cues.
            T.ColorJitter(brightness=0.15, contrast=0.15),
            T.ToTensor(),
            T.Normalize(mean, std),
        ])
    return T.Compose([T.Resize((IMG_SIZE, IMG_SIZE)), T.ToTensor(), T.Normalize(mean, std)])


def load_split_rows(manifest: Path, split: str) -> list[dict]:
    return [r for r in csv.DictReader(Path(manifest).open()) if r["split"] == split]


class TR6Dataset(Dataset):
    def __init__(self, rows, cache_dir, transform, extra=None):
        self.items = [(Path(cache_dir) / f"{r['sha256']}.jpg", PRODUCE_CLASSES.index(r["produce_class"]),
                       SPOILAGE_CLASSES.index(r["source_label"]), r["sample_id"]) for r in rows]
        if extra:  # list of (path, produce_idx, spoil_idx, id) — e.g. GAN images (train only)
            self.items += extra
        self.transform = transform

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        p, yt, ys, sid = self.items[i]
        img = Image.open(p).convert("RGB")
        return self.transform(img), yt, ys, sid


# ---------------- deterministic corruptions (evaluation only) ----------------
def corrupt(img: Image.Image, kind: str, level: float, seed: int) -> Image.Image:
    """Apply a deterministic corruption at 224x224 in [0,255] pixel space."""
    if kind == "clean":
        return img
    rng = np.random.default_rng(seed)
    a = np.asarray(img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR), dtype=np.float32) / 255.0
    if kind == "gaussian":
        a = a + rng.normal(0, level, a.shape)
    elif kind == "salt_pepper":
        m = rng.random(a.shape[:2])
        a = a.copy()
        a[m < level / 2] = 0.0
        a[(m >= level / 2) & (m < level)] = 1.0
    elif kind == "speckle":
        a = a + a * rng.normal(0, level, a.shape)
    elif kind == "brightness":
        a = a * level
    else:
        raise ValueError(kind)
    return Image.fromarray((np.clip(a, 0, 1) * 255).round().astype(np.uint8))


# ---------------- metrics ----------------
def classification_metrics(y_true, y_pred, probs, class_names):
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                 precision_recall_fscore_support, roc_auc_score)

    y_true, y_pred, probs = np.asarray(y_true), np.asarray(y_pred), np.asarray(probs)
    labels = list(range(len(class_names)))
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    out = {
        "n": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)),
        "per_class": {c: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i])}
                      for i, c in enumerate(class_names)},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "class_names": class_names,
    }
    try:
        if len(class_names) == 2:
            out["roc_auc"] = float(roc_auc_score(y_true, probs[:, 1]))
        else:
            out["roc_auc_ovr_macro"] = float(roc_auc_score(y_true, probs, multi_class="ovr", average="macro",
                                                           labels=labels))
    except ValueError as e:
        out["roc_auc_error"] = str(e)
    return out


def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2))
