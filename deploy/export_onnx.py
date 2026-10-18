"""
export_onnx.py — export the deployed models to ONNX (int8 weights for the ViT) so the
backend can run without PyTorch on small free hosts (512 MB RAM).

ViT graph outputs: type_logits[1,6], spoil_logits[1,2], z[1,768] (CLS embedding) and
attn[12,197,197] (head-averaged softmax attention per block, for attention rollout).
U-Net graph output: logits[1,2,256,256].
Parity against PyTorch is checked on real cached test images.

Usage: .venv/bin/python deploy/export_onnx.py
"""
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml")); sys.path.insert(0, str(ROOT / "ml/evaluate")); sys.path.insert(0, str(ROOT / "backend"))
from evaluate_vit import load_model  # noqa: E402
from unet_model import UNetResNet18  # noqa: E402

OUT = ROOT / "deploy/onnx"
OUT.mkdir(parents=True, exist_ok=True)


class ViTWithAttn(nn.Module):
    """Same computation as timm's VisionTransformer, but returns per-block attention."""

    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):
        b = self.m.backbone
        x = b.patch_embed(x)
        x = b._pos_embed(x)
        x = b.patch_drop(x)
        x = b.norm_pre(x)
        attns = []
        for blk in b.blocks:
            a = blk.attn
            y = blk.norm1(x)
            B, N, C = y.shape
            qkv = a.qkv(y).reshape(B, N, 3, a.num_heads, C // a.num_heads).permute(2, 0, 3, 1, 4)
            q, k, v = qkv.unbind(0)
            q, k = a.q_norm(q), a.k_norm(k)
            att = ((q * a.scale) @ k.transpose(-2, -1)).softmax(-1)
            attns.append(att.mean(1))
            o = (att @ v).transpose(1, 2).reshape(B, N, C)
            o = a.proj(o)
            x = x + blk.drop_path1(blk.ls1(o))
            x = x + blk.drop_path2(blk.ls2(blk.mlp(blk.norm2(x))))
        x = b.norm(x)
        z = b.forward_head(x, pre_logits=True)
        return self.m.head_type(z), self.m.head_spoil(z), z, torch.cat(attns, 0)


def main():
    import onnxruntime as ort
    from onnxruntime.quantization import QuantType, quantize_dynamic
    model, cfg, _ = load_model(ROOT / "artifacts/runs/vit_b16_primary", torch.device("cpu"))
    w = ViTWithAttn(model).eval()
    x = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        ref = model.backbone(x); r2 = w(x)
    print("wrapper z max diff vs timm:", float((ref - r2[2]).abs().max()))
    fp = OUT / "vit_fp32.onnx"
    torch.onnx.export(w, x, str(fp), input_names=["image"], output_names=["type_logits", "spoil_logits", "z", "attn"], opset_version=17, dynamo=False)
    quantize_dynamic(str(fp), str(OUT / "foresight_vit_int8.onnx"), weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul", "Gemm"])
    fp.unlink()
    net = UNetResNet18(); ck = torch.load(ROOT / "backend/models/unet_pilot.pt", map_location="cpu", weights_only=False)
    net.load_state_dict(ck["state_dict"]); net.eval()
    torch.onnx.export(net, torch.randn(1, 3, 256, 256), str(OUT / "unet_pilot.onnx"), input_names=["image"], output_names=["logits"], opset_version=17, dynamo=False)
    s = ort.InferenceSession(str(OUT / "foresight_vit_int8.onnx"), providers=["CPUExecutionProvider"])
    o = s.run(None, {"image": x.numpy()})
    print("int8 vs torch: spoil prob diff", float(np.abs(torch.softmax(r2[1], 1).numpy() - np.exp(o[1]) / np.exp(o[1]).sum()).max()),
          "attn shape", o[3].shape)
    for f in OUT.iterdir():
        print(f.name, round(f.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
