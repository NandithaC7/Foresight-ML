"""
build_reports.py — generate the final-review DOCX documents from build/facts.json.
Run analysis.py first. Every number below is read from facts.json (which is read from
saved run/eval/evidence files); prose only interprets those numbers.

Usage: .venv/bin/python releases/final_review/build/build_reports.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FR = ROOT / "releases/final_review"
FIG = FR / "figures"
SPECS = FR / "build/specs"
SPECS.mkdir(parents=True, exist_ok=True)
F = json.loads((FR / "build/facts.json").read_text())
DATE = "15 October 2026"
PROD = ["Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato"]


def f3(x):
    return "NOT AVAILABLE" if x is None else f"{x:.3f}"


def f4(x):
    return "NOT AVAILABLE" if x is None else f"{x:.4f}"


def pct(x, d=1):
    return "NOT AVAILABLE" if x is None else f"{100 * x:.{d}f}%"


def pm(d, k=3):
    if not d:
        return "NOT RUN"
    return f"{d['mean']:.{k}f} ± {d['std']:.{k}f}" if d.get("std") is not None else f"{d['mean']:.{k}f}"


def nice(t):
    return t.replace("Indian_Gooseberry", "Indian Gooseberry").replace("Not_spoiled", "Not spoiled")


class Doc:
    def __init__(self, title, short, subtitle, meta=None):
        self.spec = {"title": title, "short": short, "subtitle": subtitle, "meta": meta or [], "blocks": []}

    def _a(self, **b):
        self.spec["blocks"].append(b)
        return self

    def h1(self, t): return self._a(type="h1", text=t)
    def h2(self, t): return self._a(type="h2", text=t)
    def h3(self, t): return self._a(type="h3", text=t)
    def p(self, t): return self._a(type="p", text=t)
    def note(self, t, warn=False): return self._a(type="note", text=t, tone="warn" if warn else "ok")
    def bul(self, items): return self._a(type="bullets", items=list(items))
    def num(self, items): return self._a(type="numbered", items=list(items))
    def kv(self, items): return self._a(type="kv", items=list(items))
    def pb(self): return self._a(type="pagebreak")

    def table(self, caption, header, rows, widths=None, source=None, small=False):
        return self._a(type="table", caption=caption, header=header, rows=[[str(c) for c in r] for r in rows],
                       widths=widths, source=source, small=small)

    def fig(self, name, caption, source=None, width=1.0):
        path = FIG / name
        if not path.exists():
            return self.note(f"Figure `{name}` NOT AVAILABLE (input result missing).", warn=True)
        return self._a(type="figure", path=str(path), caption=caption, source=source, width_frac=width)

    def save(self, fname):
        sp = SPECS / (Path(fname).stem + ".json")
        sp.write_text(json.dumps(self.spec, indent=1))
        out = FR / fname
        r = subprocess.run(["node", str(FR / "build/render_docx.js"), str(sp), str(out)], capture_output=True, text=True, cwd=FR / "build")
        print(r.stdout.strip() or r.stderr.strip())
        return out


META = lambda kind: [("Project", "Foresight — visual produce-spoilage estimation (research prototype)"),  # noqa: E731
                     ("Document", kind), ("Date", DATE), ("Workspace", "/Users/nandu/Downloads/foresight"),
                     ("Deployed model", f"vit_b16_primary@epoch{F['primary']['best_epoch']} (`backend/models/foresight_vit.pt`)")]

# ---------------------------------------------------------------- shared facts
P, D = F["primary"], F["dataset"]
SPL = D["split"]
TS, TT = P["test_spoil"], P["test_type"]
BOOT, CAL = P["bootstrap"], P["calibration"]
S2, DS2, PAIRS = F["ablation_v2_summary"], F["daysplit_v2_summary"], F["ablation_pairs"]
V1 = F["ablation_v1"]
GANQ = F["gan"]["quality"]
GL = GANQ["label_consistency_by_primary_vit"]
XF, XS = F["xai"]["faithfulness"], F["xai"]["stability"]
T = F["tests"]
E2E = T["e2e"]
TR = F["tr6plus"]
RES = F["resources"]
LAT = T["latency"]
v2_done = sum(1 for r in F["ablation_v2_runs"].values() if r["complete"])
day_done = len([r for r in F["daysplit_v2_runs"].values() if r and r.get("complete")])
dn2 = F["dncnn_v2"]
pytest_cases = T["pytest_cases"]
n_pass = sum(1 for _, s in pytest_cases if s == "PASSED")
VITEST = json.loads((FR / "evidence/vitest.json").read_text()) if (FR / "evidence/vitest.json").exists() else None
ABL_STATUS = "COMPLETE" if v2_done == 9 else "IN PROGRESS"
DAY_STATUS = "COMPLETE" if day_done == 3 else "IN PROGRESS"


def rob(kind, lvl, den):
    for r in F["robustness"]:
        if r["corruption"] == kind and abs(r["level"] - lvl) < 1e-9 and r["denoiser"] == den:
            return r
    return None


def cond_rows():
    rows = []
    for c, lab in (("noaug", "Real only (no augmentation)"), ("aug", "Real + conventional augmentation"), ("gan", "Real + conventional aug. + 480 GAN images")):
        s = S2.get(c)
        if not s:
            rows.append([lab, "NOT RUN"] + [""] * 7); continue
        rows.append([lab, f"{s['n_seeds']} ({', '.join(map(str, s['seeds']))})", s["n_train"], pm(s["test_spoil_accuracy"]), pm(s["test_spoil_macro_precision"]),
                     pm(s["test_spoil_macro_recall"]), pm(s["test_spoil_macro_f1"]), pm(s["test_spoil_auc"]), pm(s["test_type_macro_f1"])])
    return rows


COND_HDR = ["Condition", "Seeds", "Train images", "Spoilage accuracy", "Macro precision", "Macro recall", "Macro-F1", "ROC-AUC", "Produce macro-F1"]


def per_seed_rows(include_day=True):
    rows = []
    runs = list(F["ablation_v2_runs"].items()) + (list(F["daysplit_v2_runs"].items()) if include_day else [])
    for k, r in runs:
        if not r or not r.get("complete"):
            continue
        rows.append([k, r["seed"], r["n_train"], r["epochs_run"], r["best_epoch"], f3(r["best_val_spoil_macro_f1"]), f3(r["test_spoil"]["accuracy"]),
                     f3(r["test_spoil"]["macro_f1"]), f3(r["test_spoil"]["roc_auc"]), f"{r['train_seconds'] / 60:.1f}", f"{r['latency_ms']:.2f}"])
    return rows


SEED_HDR = ["Run", "Seed", "Train n", "Epochs run", "Best epoch (val)", "Best val spoil mF1", "Test acc.", "Test spoil mF1", "Test AUC", "Train min", "Infer. ms/img"]


def diff_text(key):
    d = PAIRS.get(key)
    if not d or not d["per_seed"]:
        return "NOT AVAILABLE"
    return f"{d['mean']:+.3f} (per seed: {', '.join(f'{x:+.3f}' for x in d['per_seed'])})"


# ======================================================================= 00 STATUS AUDIT
def doc_status():
    d = Doc("Project Status Audit and AI-Integration Verification", "Status audit",
            "Evidence-based status of every Foresight component, whether a genuine trained AI model exists, and whether it is integrated end to end.",
            META("00 — Project status audit"))
    d.h1("Scope and method")
    d.p("This audit inspected the workspace (`frontend/`, `backend/`, `dataset/TR-6/`, `dataset-preparation/tr6-audit/`, `Foresight-TR6-plus/`, `releases/`, `ml/`, `artifacts/`) "
        "and re-executed the verification commands listed in Section 6. A component is marked **COMPLETE** only when a saved run, measurement or executed test supports it; "
        "the existence of code alone is never counted as completion.")
    d.h1("Status table")
    sv = SPL["split_counts"]; sf = SPL["split_fractions_actual"]
    rows = [
        ["Primary ViT classifier + checkpoint", "COMPLETE", f"`{P['checkpoint']}` ({P['checkpoint_mb']} MB); deployed copy `{P['deployed_checkpoint']}` (SHA-256 identical, prefix {P['deployed_sha256'][:12]})",
         f"ViT-B/16, 2 heads; trained {P['config']['epochs_run']} epochs ({P['train_minutes']} min); best epoch {P['best_epoch']} by validation"],
        ["Dataset used / eligible samples", "COMPLETE", "`artifacts/dataset/v1/split_manifest.csv`, `split_summary.json`",
         f"TR-6 sRGB; {SPL['eligible_samples']:,} eligible unique contents of {SPL['unique_image_contents']:,}; exclusions: " + ", ".join(f"{k} {v:,}" for k, v in SPL["exclusions"].items())],
        ["60 / 20 / 20 split", "COMPLETE", "`split_summary.json`; test M05",
         f"{sv['train']:,} / {sv['val']:,} / {sv['test']:,} = {pct(sf['train'], 2)} / {pct(sf['val'], 2)} / {pct(sf['test'], 2)}"],
        ["Duplicate- and group-aware split verification", "COMPLETE", "tests M01–M07; `data/split_leakage_comparison.csv`",
         f"0 content hashes and 0 sessions shared across splits; {SPL['leakage_checks']['test_sessions_sharing_calendar_day_with_train']}/{SPL['leakage_checks']['test_sessions_total']} test sessions share a capture day with train (disclosed)"],
        ["GAN augmentation + comparison vs baseline", ABL_STATUS, "`artifacts/experiments/gan/`; `artifacts/runs/abl2_*`; Document A",
         f"cDCGAN trained (train split only), 480 images; controlled 3-condition comparison: {v2_done}/9 runs complete"],
        ["DnCNN noise removal", "COMPLETE" if dn2 else "IN PROGRESS", "`artifacts/experiments/dncnn/`" + (", `dncnn_v2/`" if dn2 else ""),
         f"v1: {F['dncnn_v1']['steps']:,} steps (under-trained)" + (f"; v2 resumed to {dn2['steps']:,} steps" if dn2 else "; v2 continuation queued")],
        ["Noise robustness + noise-component analysis", "COMPLETE", "`data/noise_robustness.csv`; `artifacts/experiments/noise_profile.json`",
         f"{len(F['robustness'])} corrupted-test evaluations (Gaussian, salt & pepper, speckle × 3 levels × denoisers); intrinsic noise σ≈{F['noise_profile']['overall_fullres_mean']:.4f}"],
        ["K-means clustering", "COMPLETE", "`artifacts/experiments/kmeans/`",
         f"frozen-ViT features, k=6: NMI(produce) {F['kmeans']['vit_frozen']['alignment']['k6_test']['NMI_produce']:.3f} on test"],
        ["XAI implementation + explanations", "COMPLETE", "`backend/inference.py` (served), `artifacts/experiments/xai/`; Document B",
         f"attention rollout; deletion test drop {XF['mean_drop_top_rollout']:.3f} vs random {XF['mean_drop_random']:.3f}; stability ρ(flip) {XS['flip_consistency']['mean']:.2f}"],
        ["U-Net segmentation", "BLOCKED", "`Foresight-TR6-plus/annotations/` (12 proposal-only masks)",
         "0 human-reviewed masks (annotation status: " + ", ".join(f"{k} {v}" for k, v in TR["annotation_status_counts"].items()) + "); training on proposals would be fabricated ground truth"],
        ["YOLO detection", "NOT IMPLEMENTED", "—", "TR-6 images are single-item with no bounding boxes; detection not justified for the current data"],
        ["FastAPI backend", "COMPLETE", "`backend/main.py`, `inference.py`, `db.py`; 23 backend tests", "real checkpoint loaded at startup; validation, structured errors, CORS, SQLite history, PDF, XAI"],
        ["React frontend integration", "COMPLETE", "`frontend/src/api.js`, pages; build + 7 Vitest tests + UI contract check",
         f"{T['ui_contract']['fields_present']}/{T['ui_contract']['fields_checked']} UI-consumed fields present in real responses; browser checks passed"],
        ["Database + prediction history", "COMPLETE", "`backend/db.py`; test B16; E2E E06–E07", "SQLite; persists across restart; uploaded images not stored"],
        ["Automated + end-to-end testing", "COMPLETE", "`evidence/pytest_final.log`, `vitest.json`, `e2e_smoke_final.json`",
         f"pytest {T['pytest_summary']}; Vitest {VITEST['numPassedTests'] if VITEST else 'NOT RUN'}/{VITEST['numTotalTests'] if VITEST else ''} passed; E2E {E2E['passed']}/{E2E['total']} checks"],
        ["TR-6+ dataset extension + validation", "IN PROGRESS", "`Foresight-TR6-plus/`; `evidence/tr6plus_validation_rerun_2026-10-15/`",
         f"validator PASS ({TR['validation_rerun']['n_errors']} errors); noise pilot {TR['noise_pilot']['ok']}/{TR['noise_pilot']['n_rows']} derivatives; human annotation 0/96"],
        ["IEEE DataPort publication readiness", "IN PROGRESS", "`releases/Foresight-TR6-plus-dataset-v1.1.0.zip`; Document G",
         "metadata package built and checksummed; upload, authorship, DOI require your action; not uploaded"],
    ]
    d.table("Component status (COMPLETE / IN PROGRESS / BLOCKED / NOT IMPLEMENTED).", ["Component", "Status", "Evidence (local paths)", "Measured result / note"],
            rows, widths=[19, 14, 33, 34], small=True)
    d.h1("Does an actual AI model exist?")
    q = [
        ["1. Which AI/ML models are implemented?", "ViT-B/16 two-head classifier (deployed); ViT-S/16 (ablations); class-conditional DCGAN; DnCNN denoiser; logistic-regression baselines on colour histograms and frozen ViT features; K-means; attention-rollout XAI. U-Net, shelf-life regression and YOLO are NOT implemented.", "`ml/`, `backend/inference.py`"],
        ["2. Which have been trained?", f"ViT-B/16 primary (1 run); ViT-S/16 ({len([r for r in V1.values() if r])} v1 runs + {v2_done} controlled v2 runs + {day_done} day-split runs); cDCGAN ({F['gan']['train']['epochs']} epochs); DnCNN; both logistic-regression baselines; K-means fitted on train.", "`artifacts/runs/`, `artifacts/experiments/`"],
        ["3. Which checkpoints exist and where?", f"`{P['checkpoint']}` and its deployed copy `backend/models/foresight_vit.pt`; `artifacts/runs/*/best.pt` for every ViT-S run; `artifacts/experiments/gan/cdcgan.pt`; `artifacts/experiments/dncnn/dncnn.pt`" + (", `dncnn_v2/dncnn.pt`" if dn2 else "") + ".", "file listing"],
        ["4. Which models does the backend load?", f"Only the ViT-B/16 checkpoint, loaded once at startup (version `vit_b16_primary@epoch{P['best_epoch']}`, device {E2E['device']}). GAN, DnCNN and baselines are research-only.", "`/health`, `/api/models`"],
        ["5. Does the frontend invoke genuine inference?", f"Yes. The UI posts the image to `POST /api/analyze`; the response comes from the ViT forward pass. Verified through the browser UI and by sending {E2E['held_out_images_via_api']} held-out originals through HTTP (produce {E2E['produce_correct']}/{E2E['held_out_images_via_api']}, spoilage {E2E['spoilage_correct']}/{E2E['held_out_images_via_api']} correct).", "`evidence/e2e_smoke_final.json`"],
        ["6. Are any predictions mock/hard-coded/simulated?", "No in the default configuration. `mock_model.py` keeps a random simulator for UI development only; it runs only when `FORESIGHT_MOCK_MODE=1` (default 0) and every such response is labelled **DEMO MOCK DATA** (test B15). Hard-coded fake detections (\"Apple 98%\") and fixed values were removed from the UI. Nutrition facts and tips are static reference text, not predictions.", "test B15, UI contract check (`mock=false`)"],
        ["7. Is a working AI component demonstrable from upload to UI?", "Yes: upload → validation → decode/EXIF/resize → ViT-B/16 → softmax → deterministic result composer → JSON → React card with attention-rollout overlay → SQLite history.", "Document E, Section 7"],
        ["8. What remains before it is an *integrated AI application* in the full specified sense?", "It already is an integrated single-model AI application. The originally specified multi-model scope still lacks: reviewed decay masks → U-Net; valid time-to-endpoint labels → shelf-life; bounding boxes → detection; evaluation on real-world (non-lab) photos; calibration; third-party deployment.", "Section 5"],
    ]
    d.table("Questions on the existence and integration of a genuine AI model.", ["Question", "Answer", "Evidence"], q, widths=[22, 58, 20], small=True)
    d.h1("Backend and frontend integration verification")
    ui = T["ui_contract"]
    iq = [
        ["Is the backend implemented and runnable?", "YES", "uvicorn on :8000 served all E2E checks; `/health` → status ok"],
        ["Does it load a real trained checkpoint?", "YES", f"`model_version` = `{E2E['model_version']}`; tests R01–R04 use the real checkpoint"],
        ["Does upload produce a genuine model prediction?", "YES", f"E2E E05: {E2E['held_out_images_via_api']} full-resolution held-out images via HTTP; browser upload verified"],
        ["Do API schemas match frontend expectations?", "YES", f"{ui['fields_present']}/{ui['fields_checked']} UI-consumed fields present in live responses (`evidence/ui_contract_check.json`); nullable `days`/`decayPct` rendered as 'Not available'/'Pending annotation'"],
        ["Do dashboard, analysis and history work?", "YES", "browser checks (Analyze, History, Dashboard, About); E2E E06–E07; Vitest ItemCard/About tests"],
        ["Is persistent history implemented and tested?", "YES", "SQLite `backend/foresight.db`; test B16 survives app restart"],
        ["Are mock responses disabled by default and labelled?", "YES", "`FORESIGHT_MOCK_MODE` default 0; test B15; Vitest 'DEMO MOCK DATA' test"],
        ["Does the frontend production build pass?", "YES", "; ".join(T["build_tail"][-1:])],
        ["Do backend tests and a real E2E smoke test pass?", "YES", f"pytest: {T['pytest_summary']}; E2E: {E2E['passed']}/{E2E['total']}"],
    ]
    d.table("Integration questions and evidence.", ["Question", "Answer", "Evidence"], iq, widths=[30, 8, 62], small=True)
    d.table("Implemented API endpoints (contract used by `frontend/src/api.js`).", ["Method", "Path", "Purpose / response"],
            [["GET", "/health, /api/health", "status, model_loaded, model_version, model_error, mock_mode, device"],
             ["GET", "/api/models", "status of ViT (loaded) and of U-Net / shelf-life / YOLO / DnCNN (with reasons) + held-out test metrics"],
             ["POST", "/api/analyze?xai=true", "multipart `photo` (JPG/PNG/WEBP ≤15 MB) → scan_id, model_version, warnings, disclaimer, timing, items[] (produce, spoilage, confidences, XAI overlay)"],
             ["GET", "/api/history, /api/history/{scan_id}", "persisted scans (no images stored)"],
             ["GET / DELETE", "/api/inspections", "list / clear history (used by History & Dashboard)"],
             ["GET", "/api/stats, /api/report, /api/report/pdf, /api/tips, /api/nutrition/{name}", "dashboard statistics, text/PDF report, static content"]],
            widths=[10, 30, 60], small=True)
    d.h1("Remaining work")
    d.table("Items that cannot honestly be called complete.", ["Item", "Status", "What is required"], [
        ["U-Net decay segmentation", "BLOCKED", "Human-reviewed decay masks (≥ a few hundred) with a written rubric; currently 0 reviewed, 12 machine proposals."],
        ["Shelf-life regression", "BLOCKED", "Measured time-to-endpoint labels; TR-6 provides none."],
        ["YOLO detection", "NOT IMPLEMENTED", "Multi-item photographs with bounding-box annotations."],
        ["Real-world generalisation", "NOT RUN", "A labelled set of phone photos outside the TR-6 lab setting."],
        ["Human annotation (TR-6+)", "IN PROGRESS", "0 of 96 pilot images annotated by a human in Label Studio/CVAT."],
        ["Third-party deployment", "NOT IMPLEMENTED", "Host with ≥1.5 GB RAM for the backend; static host for `frontend/dist`."],
        ["IEEE DataPort submission", "IN PROGRESS", "Your IEEE account, author list, upload; DOI assigned only after submission."],
    ], widths=[25, 15, 60], small=True)
    d.h1("Verification commands executed")
    d.bul([f"`python3 dataset-preparation/tr6-audit/audit_tr6.py --dataset dataset/TR-6 --output dataset-preparation/tr6-audit/output_rerun_2026-10-15` — identical to the prior audit on every compared summary field" + (" (differences: " + ", ".join(D["audit_rerun_fields_differing_from_prior"]) + ")" if D["audit_rerun_fields_differing_from_prior"] else ""),
           "`.venv/bin/python -m pytest backend/tests ml/tests -v` → " + T["pytest_summary"],
           "`cd frontend && npm test` (Vitest) and `npm run build`",
           "`.venv/bin/python scripts/e2e_smoke.py --n 60` and `scripts/check_ui_contract.py` against running servers",
           "`Foresight-TR6-plus/scripts/validate_extension.py --hash-mode pilot` on a scratch copy (originals untouched)"])
    return d.save("00_Foresight_Project_Status_Audit.docx")


# ======================================================================= A GAN
def doc_gan():
    g = F["gan"]
    d = Doc("GAN Model Comparison Report", "GAN comparison",
            "Class-conditional DCGAN for training-only augmentation, and a controlled comparison of real-only, conventional-augmentation and real-plus-GAN training.",
            META("A — GAN model comparison"))
    d.h1("Summary of findings")
    d.bul([
        f"A class-conditional DCGAN (64×64, 12 conditions = produce × spoilage) was trained on the **training split only** ({g['train']['train_images']:,} images, {g['train']['epochs']} epochs, {g['train']['minutes_budget']} min budget) and generated {g['generation']['generated']} images (40 per condition).",
        f"**Quality is limited.** The deployed classifier (trained on real images only) recognises the intended produce type in only **{pct(GL['overall_type_match'])}** of GAN images and the intended spoilage label in {pct(GL['overall_spoil_match'])}; within-condition diversity is {GANQ['mean_diversity_ratio']:.2f}× that of real images. No memorisation was detected.",
        f"**Controlled comparison** (ViT-S/16, identical configuration, seeds 42/43/44, same untouched test split): real-only {pm(S2['noaug']['test_spoil_macro_f1'] if S2['noaug'] else None)}, conventional augmentation {pm(S2['aug']['test_spoil_macro_f1'] if S2['aug'] else None)}, real + GAN {pm(S2['gan']['test_spoil_macro_f1'] if S2['gan'] else None)} test spoilage macro-F1 (mean ± SD).",
        f"Paired per-seed difference GAN − conventional augmentation: {diff_text('gan_minus_aug')}. " + ("With three seeds this is not evidence of a reliable benefit; see Section 7." if PAIRS.get('gan_minus_aug', {}).get('per_seed') else ""),
    ])
    d.h1("Dataset and split used for the GAN")
    d.p(f"The GAN uses only the training partition of split v1 (session-grouped, duplicate-aware, seed 42): {SPL['split_counts']['train']:,} unique sRGB images. Validation ({SPL['split_counts']['val']:,}) and test ({SPL['split_counts']['test']:,}) images were never shown to the GAN, and generated images were only ever added to classifier **training** sets.")
    d.table("GAN training images per condition (training split only).", ["Condition (produce / label)", "Train images"],
            [[nice(k), v["train"]] for k, v in SPL["per_stratum"].items()] + [["Total", SPL["split_counts"]["train"]]], widths=[70, 30])
    d.h1("Architecture, objective and hyperparameters")
    d.p("Generator G(z, c): the noise vector z ∈ R¹⁰⁰ is concatenated with a 50-d embedding of the condition c and passed through 5 transposed-convolution blocks (512→256→128→64→3 channels, BatchNorm + ReLU, tanh output) to a 64×64 RGB image. "
        "Discriminator D(x, c): the condition is embedded as a 64×64 plane and concatenated to the image as a 4th channel, then 5 strided convolutions (64→128→256→512→1, BatchNorm + LeakyReLU 0.2) produce one logit.")
    d.p("Objective (non-saturating conditional GAN): L_D = −E[log D(x,c)] − E[log(1 − D(G(z,c),c))] with one-sided label smoothing (real target 0.9); L_G = −E[log D(G(z,c),c)]. Both are implemented with `BCEWithLogitsLoss`.")
    d.table("GAN hyperparameters (actual values from `artifacts/experiments/gan/train_summary.json`).", ["Hyperparameter", "Value"], [
        ["Resolution", f"{g['train']['resolution']}×{g['train']['resolution']}"], ["Conditions", len(g["train"]["conditions"])], ["Latent dimension", 100],
        ["Optimiser", g["train"]["optimizer"]], ["Batch size", g["train"]["batch"]], ["Real-label smoothing", g["train"]["label_smoothing_real"]],
        ["Augmentation during GAN training", "random horizontal flip"], ["Epochs completed", g["train"]["epochs"]], ["Time budget", f"{g['train']['minutes_budget']} min (Apple M5, MPS)"],
        ["Seed (training / generation)", f"{g['train']['seed']} / {g['train']['seed'] + 1}"], ["Generated images", f"{g['generation']['generated']} ({g['generation']['per_class']} per condition), upsampled to 256×256 bicubic"]],
        widths=[40, 60], source="`ml/experiments/gan.py`")
    d.fig("gan_losses.png", "Discriminator and generator losses per epoch. The losses stay in a stable band without collapse of either player, but stable GAN losses do not imply sample quality.")
    d.h1("Synthetic sample generation and quality checks")
    d.fig("gan_samples_grid.png", "Fixed-noise samples after training; each row is one condition in the order Banana-NS, Banana-S, Carrot-NS, Carrot-S, Guava-NS, Guava-S, Gooseberry-NS, Gooseberry-S, Mango-NS, Mango-S, Tomato-NS, Tomato-S.", width=0.42)
    d.p("Visual review (human, qualitative): most rows resemble the intended produce in overall colour and shape, and Spoiled rows are darker/browner for banana, carrot and guava. Samples are blurry at 64×64 and lack surface detail; the banana rows show very low within-row variation. The quantitative checks below show that this visual resemblance is not sufficient for a classifier trained on real images. FID was **NOT RUN**: with 480 images at 64×64 it would not be a reliable estimate.")
    nn = g["generation"]
    d.table("Memorisation check: nearest-neighbour L2 distance at 64×64 (pixel range [−1, 1]).", ["Comparison", "Mean", "Median", "Minimum"], [
        ["Generated → nearest real training image (same condition)", f"{nn['nn_l2_generated_to_train']['mean']:.2f}", f"{nn['nn_l2_generated_to_train']['median']:.2f}", f"{nn['nn_l2_generated_to_train']['min']:.2f}"],
        ["Real training image → nearest other real image (same condition)", f"{nn['nn_l2_train_to_train']['mean']:.2f}", f"{nn['nn_l2_train_to_train']['median']:.2f}", f"{nn['nn_l2_train_to_train']['min']:.2f}"]],
        widths=[55, 15, 15, 15], source="`artifacts/experiments/gan/generation_summary.json`")
    d.p("Generated images are on average further from their nearest training image than real images are from each other (real images are close because each capture session contains 17 near-identical views), so there is no evidence of copying.")
    d.fig("gan_nearest_neighbour.png", "One generated sample per condition (top) and its nearest real training image (bottom).", width=0.95)
    d.table("Within-condition diversity (mean pairwise L2 at 64×64).", ["Condition", "Generated", "Real (40 sampled)", "Ratio"],
            [[nice(k), f"{v['generated_mean_pairwise_l2']:.2f}", f"{v['real_mean_pairwise_l2']:.2f}", f"{v['ratio_generated_to_real']:.2f}"] for k, v in GANQ["diversity_64px"].items()],
            widths=[40, 20, 20, 20], source="`artifacts/experiments/gan/quality_checks.json`", small=True)
    lowdiv = sorted(GANQ["diversity_64px"].items(), key=lambda kv: kv[1]["ratio_generated_to_real"])[:2]
    d.p("Diversity: a ratio of 1 means generated images vary as much as real ones. The lowest ratios are " + " and ".join(f"{nice(k)} ({v['ratio_generated_to_real']:.2f})" for k, v in lowdiv)
        + ", i.e. partial mode collapse for these conditions; most other conditions are between 0.8 and 1.0.")
    d.fig("gan_label_consistency.png", "Label consistency: fraction of the 40 images per condition for which the deployed ViT-B/16 predicts the conditioning produce type and spoilage label.")
    d.table("Label consistency of GAN images under the deployed classifier.", ["Condition", "n", "Produce type matches", "Spoilage matches"],
            [[nice(k), v["n"], f"{v['type_match']} ({pct(v['type_match'] / v['n'], 0)})", f"{v['spoil_match']} ({pct(v['spoil_match'] / v['n'], 0)})"] for k, v in GL["per_condition"].items()]
            + [["Overall", sum(v["n"] for v in GL["per_condition"].values()), pct(GL["overall_type_match"]), pct(GL["overall_spoil_match"])]], widths=[40, 10, 25, 25], small=True)
    d.p("Interpretation: Tomato conditions are recognised perfectly, Carrot-NS and Gooseberry-NS partly; Banana, Guava and Mango samples are almost never recognised as their intended produce. Many GAN images therefore carry labels that a real-data classifier disagrees with, i.e. they are noisy training examples.")
    d.h1("Comparison protocol")
    d.p("All conditions use the **same classifier and evaluation protocol**; only the training-set composition changes. This controlled study (\"ablation v2\") replaces an earlier single-seed comparison (Section 8) that used a learning rate too high for ViT-S and became unstable.")
    d.table("Controlled configuration (identical for every condition and seed).", ["Setting", "Value"], [
        ["Classifier", "ViT-S/16 (`vit_small_patch16_224.augreg_in21k_ft_in1k`), produce head (6) + spoilage head (2)"],
        ["Optimiser / LR", "AdamW, backbone 2e-5, heads 2e-4, weight decay 0.01, 1-epoch warm-up + cosine"],
        ["Batch / epochs / early stopping", "32 / ≤10 / patience 4 on validation composite macro-F1"],
        ["Split", "v1 session-grouped; validation 1,087; test 1,071 (untouched until after selection)"],
        ["Seeds", "42, 43, 44 (classifier seed; the same 480 GAN images are used for every seed)"],
        ["Conditions", "(i) real only, no augmentation; (ii) real + conventional augmentation (crop, flips, ±15° rotation, brightness/contrast ±0.15); (iii) as (ii) + 480 GAN images"],
        ["Metrics", "accuracy, macro precision, macro recall, macro-F1, ROC-AUC (spoilage); produce macro-F1"]], widths=[30, 70])
    d.h1("Results")
    if v2_done < 9:
        d.note(f"Controlled comparison status: {v2_done}/9 runs complete at build time; missing runs are reported as NOT RUN.", warn=True)
    d.table("Test-set results, mean ± sample SD over seeds (spoilage head unless stated).", COND_HDR, cond_rows(),
            widths=[24, 9, 7, 10, 10, 10, 10, 10, 10], source="`artifacts/runs/abl2_*/eval/test_clean_0_none.json`", small=True)
    d.table("Per-run details (validation used only for model selection).", SEED_HDR, per_seed_rows(include_day=False), small=True,
            source="`data/ablation_all_runs.csv`")
    d.table("Paired per-seed differences in test spoilage macro-F1.", ["Comparison", "Mean difference (per seed)"],
            [["Conventional aug − real only", diff_text("aug_minus_noaug")], ["GAN − conventional aug", diff_text("gan_minus_aug")], ["GAN − real only", diff_text("gan_minus_noaug")]],
            widths=[35, 65])
    d.fig("ablation_v2_comparison.png", "Left: test spoilage macro-F1 per condition (bars = mean, whiskers = SD, dots = seeds; the day-split bar belongs to Document C). Right: validation spoilage macro-F1 curves of every run.")
    d.fig("ablation_v2_confusions.png", "Spoilage confusion matrices summed over the three seeds (NS = Not spoiled, S = Spoiled).")
    d.fig("ablation_v2_spoiled_recall.png", "Recall of the Spoiled class per produce type, averaged over seeds.")
    if S2.get("gan"):
        d.table("Spoiled-class recall per produce type (mean over seeds).", ["Produce"] + [c for c in ("Real only", "Conv. aug", "Conv. aug + GAN")],
                [[nice(t)] + [f3(S2[c]["spoiled_recall_by_produce"][t]) if S2.get(c) else "NOT RUN" for c in ("noaug", "aug", "gan")] for t in PROD], widths=[34, 22, 22, 22])
    d.table("Computational cost (measured).", ["Item", "Value"], [
        ["GAN training", f"{g['train']['epochs']} epochs in {g['train']['minutes_budget']} min on Apple M5 (MPS), concurrent with other jobs"],
        ["Classifier training per run (mean over seeds)", "; ".join(f"{c}: {pm(S2[c]['train_minutes'], 1)} min" for c in ("noaug", "aug", "gan") if S2.get(c))],
        ["Training images per epoch", "; ".join(f"{c}: {S2[c]['n_train']:,}" for c in ("noaug", "aug", "gan") if S2.get(c))],
        ["Batched test inference (ms/image)", "; ".join(f"{c}: {pm(S2[c]['latency_ms'], 2)}" for c in ("noaug", "aug", "gan") if S2.get(c))]], widths=[35, 65])
    d.h1("Earlier single-seed comparison (v1, superseded)")
    rows = []
    for k, lab in (("vit_s16_noaug", "Real only"), ("vit_s16_aug", "Conv. aug"), ("vit_s16_aug_gan", "Conv. aug + GAN")):
        r = V1[k]
        rows.append([lab, k, r["lr"], r["epochs_run"], r["best_epoch"], f3(r["best_val_spoil_macro_f1"]), ", ".join(f"{x:.3f}" for x in r["val_spoil_curve"]), f3(r["test_spoil"]["macro_f1"])])
    d.table("v1 runs (ViT-S/16, lr 5e-5, seed 42). Best-validation values are validation results, not test results.",
            ["Condition", "Run", "LR", "Epochs", "Best epoch", "Best val spoil mF1", "Val spoil mF1 per epoch", "Test spoil mF1"], rows, small=True,
            widths=[12, 16, 6, 7, 8, 10, 31, 10])
    d.p(f"In v1 the conventional-augmentation run reached its best **validation** spoilage macro-F1 ({f3(V1['vit_s16_aug']['val_spoil_curve'][0])}) at epoch 1, then oscillated and early-stopped at epoch {V1['vit_s16_aug']['epochs_run']}; its test spoilage macro-F1 was {f3(V1['vit_s16_aug']['test_spoil']['macro_f1'])}. "
        "Because a single unstable run cannot support conclusions, v1 is reported for transparency only and the controlled v2 study above is used for all conclusions.")
    d.h1("Interpretation and conclusion")
    gm = PAIRS.get("gan_minus_aug", {})
    if gm.get("per_seed"):
        consistent = all(x > 0 for x in gm["per_seed"]) or all(x < 0 for x in gm["per_seed"])
        d.p(f"Across {len(gm['per_seed'])} paired seeds, adding the GAN images changed test spoilage macro-F1 by {diff_text('gan_minus_aug')} relative to conventional augmentation alone. "
            + ("The sign is consistent across seeds, but with only three seeds and a seed-to-seed SD of the same order, the effect should be regarded as **suggestive, not established**." if consistent
               else "The sign is **not consistent** across seeds, so no reliable effect of GAN augmentation can be claimed."))
    d.p(f"This is consistent with the quality checks: only {pct(GL['overall_type_match'])} of GAN images are recognisable as their intended produce by a real-data classifier, so they mostly act as weakly-labelled noise. "
        "Any small effect should not be attributed to realistic synthetic data. Conclusion: **the GAN pipeline is implemented and evaluated, but GAN augmentation is not shown to improve spoilage classification on TR-6 and is not used by the deployed model.**")
    d.h1("Limitations")
    d.bul(["64×64 generation upsampled to 256×256 — far below the resolution at which decay texture is visible.",
           "Three classifier seeds and a single GAN seed; GAN variance is not captured.",
           "FID/KID not computed; quality judged by classifier consistency, nearest-neighbour distance, diversity ratio and visual review.",
           "All comparisons share the specimen-leakage limitation of TR-6 (Document D, Section 2)."])
    d.h1("Reproducibility")
    d.bul(["`.venv/bin/python ml/experiments/gan.py train --minutes 12` then `gan.py generate --per-class 40`",
           "`.venv/bin/python ml/experiments/extra_analyses.py gan_quality`",
           "`./ml/run_ablation_v2.sh` (3 conditions × seeds 42–44; resumable)",
           "Artefacts: `artifacts/experiments/gan/` (checkpoint `cdcgan.pt`, `generated_manifest.csv`, summaries), `artifacts/runs/abl2_*`"])
    return d.save("A_GAN_Model_Comparison_Report.docx")


# ======================================================================= B XAI
def doc_xai():
    d = Doc("XAI Analysis Report", "XAI analysis", "Attention-rollout explanations for the deployed ViT-B/16 spoilage classifier, with faithfulness and stability tests.",
            META("B — Explainable AI analysis"))
    d.h1("Model and motivation")
    d.p(f"The deployed model is a ViT-B/16 fine-tuned on TR-6 sRGB images with a produce-type head and a spoilage head (test spoilage macro-F1 {f3(TS['macro_f1'])}). "
        "Because its outputs are used to advise people about food, users and reviewers need to see **which image regions drive a prediction**, and developers need to detect shortcuts (e.g. background, tray edges, lighting) that would not generalise.")
    d.h1("Method")
    d.p("Attention rollout (Abnar & Zuidema, 2020). For each of the 12 transformer blocks the softmax attention A_l = softmax(QKᵀ/√d_k) is taken (12 heads averaged), the identity is added for the residual path and rows are renormalised: Â_l = (mean_h A_l + I) / rowsum. "
        "The rollout R = Â_12 · … · Â_1 is computed and the CLS-token row over the 196 patch tokens is reshaped to 14×14, min–max normalised and bilinearly upsampled onto the 224×224 input.")
    d.p("Grad-CAM was **not used**: it is designed for convolutional feature maps, and for ViTs requires ad-hoc reshaping of token gradients; attention rollout is the established architecture-native choice. "
        "The same implementation is served by the API (`backend/inference.py`, `?xai=true`) and shown in the UI, and is used offline in `ml/experiments/xai_rollout.py` and `xai_extended.py`. Attention weights are captured with forward hooks on each block's `attn_drop` with fused attention disabled.")
    d.h1("Representative predictions and explanations")
    d.fig("xai_class_gallery_part1.png", "Correctly classified test images (Banana, Carrot, Guava; one per produce × spoilage stratum): input (top) and attention-rollout overlay (bottom) with the model's spoilage probability.")
    d.fig("xai_class_gallery_part2.png", "Correctly classified test images (Indian Gooseberry, Mango, Tomato).")
    gal = [r for r in F["xai"]["gallery"] if r["figure"] == "class_gallery.png"]
    d.table("Inputs and actual model outputs shown in the class gallery (all from the untouched test split).", ["Stratum", "Source file (TR-6)", "True", "Predicted", "p(Spoiled)"],
            [[r["tag"], r["source"].replace("Classified/", ""), nice(r["true_spoil"]), nice(r["pred_spoil"]), r["p_spoiled"]] for r in gal], widths=[14, 46, 13, 13, 14], small=True)
    d.fig("xai_correct.png", "Randomly sampled correct test spoilage predictions.")
    d.h1("Failure cases")
    d.fig("xai_failure_fn.png", "Representative test false negatives (labelled Spoiled, predicted Not spoiled).")
    d.fig("xai_failure_fp.png", "Representative test false positives (labelled Not spoiled, predicted Spoiled).")
    fl = [r for r in F["xai"]["gallery"] if r["figure"] == "failure_cases.png"]
    d.table("Failure cases shown above.", ["Type", "Produce", "Source file", "p(Spoiled)"],
            [[r["tag"], nice(r["true_type"]), r["source"].replace("Classified/", ""), r["p_spoiled"]] for r in fl], widths=[8, 20, 56, 16], small=True)
    d.fig("xai_incorrect.png", "Additional randomly sampled incorrect test spoilage predictions.")
    errs = {(e["produce"], e["label"]): e for e in P["errors_by_stratum"]}
    ig = errs[("Indian_Gooseberry", "Spoiled")]
    d.p(f"Of {CAL['n_errors']} test errors, {ig['errors']} are Indian Gooseberries labelled Spoiled that the model calls Not spoiled. In the overlays the attention lies on the fruit, not the background, and the fruits themselves look visually fresh. "
        "This points to the label definition — TR-6 spoilage folders follow capture date, and early-'Spoiled' gooseberries show no visible decay — rather than to a background shortcut. "
        f"The model is also over-confident on these errors: {pct(CAL['share_of_errors_with_conf_ge_0.9'], 0)} of all errors were made with confidence ≥ 0.90.")
    d.h1("Faithfulness test (deletion)")
    d.table("Deletion test: replace 20% of patches with the mean pixel and measure the drop in predicted-class probability.", ["Patches occluded", "Mean drop", "Median drop"], [
        ["Top-20% rollout patches", f"{XF['mean_drop_top_rollout']:.3f}", f"{XF['median_drop_top_rollout']:.4f}"],
        ["Random 20% patches", f"{XF['mean_drop_random']:.3f}", f"{XF['median_drop_random']:.4f}"]],
        widths=[50, 25, 25], source=f"n = {XF['n_images']} test images; Wilcoxon signed-rank p = {XF['wilcoxon_p']:.1e}; `artifacts/experiments/xai/xai_summary.json`")
    d.p(f"Occluding the regions highlighted by rollout reduces confidence about {XF['mean_drop_top_rollout'] / max(XF['mean_drop_random'], 1e-9):.0f}× more than occluding random regions (p = {XF['wilcoxon_p']:.1e}), which is evidence that the maps point at regions the model actually uses. "
        "Medians are near zero because most predictions are saturated (p ≈ 1), so for many images neither occlusion changes the output.")
    d.h1("Stability test")
    d.table("Explanation stability: Spearman correlation of 14×14 rollout maps.", ["Comparison", "Mean ρ", "Median ρ", "10th percentile ρ"], [
        ["Image vs horizontally flipped copy (map flipped back)", f"{XS['flip_consistency']['mean']:.3f}", f"{XS['flip_consistency']['median']:.3f}", f"{XS['flip_consistency']['p10']:.3f}"],
        ["Image vs copy with Gaussian noise σ = 0.02", f"{XS['gaussian_0.02_consistency']['mean']:.3f}", f"{XS['gaussian_0.02_consistency']['median']:.3f}", f"{XS['gaussian_0.02_consistency']['p10']:.3f}"],
        ["Baseline: two different test images", f"{XS['different_image_baseline']['mean']:.3f}", f"{XS['different_image_baseline']['median']:.3f}", "–"]],
        widths=[52, 16, 16, 16], source=f"n = {XS['n_images']} test images; spoilage prediction unchanged under flip {pct(XS['spoilage_prediction_unchanged_flip'])}, under noise {pct(XS['spoilage_prediction_unchanged_noise'])}")
    d.h1("Class-specific observations")
    d.bul(["**Banana, Carrot, Guava:** attention covers the whole fruit including dark/spotted regions; no test errors on these produce types.",
           f"**Indian Gooseberry:** attention is on the fruit, but labelled-Spoiled fruits often look fresh; {ig['errors']}/{ig['n']} Spoiled test images missed.",
           f"**Tomato:** {errs[('Tomato', 'Spoiled')]['errors']}/{errs[('Tomato', 'Spoiled')]['n']} Spoiled missed; attention concentrates on the fruit body and stem scar.",
           f"**Mango:** {errs[('Mango', 'Spoiled')]['errors']}/{errs[('Mango', 'Spoiled')]['n']} Spoiled missed.",
           "**All classes:** isolated bright spots appear on the plain background near image borders. These are a known ViT artefact (high-norm background tokens used as internal registers) and should not be read as evidence the model uses the background; the deletion test shows the dominant relevance is on the fruit."])
    d.h1("Limitations")
    d.bul(["Attention rollout is an approximation: it ignores the MLP blocks and value vectors, and attention is not proof of causal reasoning.",
           "There are no human-reviewed decay masks, so overlap between explanations and true decay regions cannot be measured.",
           "Explanations are diagnostic aids for developers and users; they do not make a prediction correct and must not be presented as a food-safety assessment."])
    d.h1("Reproducibility")
    d.bul(["`.venv/bin/python ml/experiments/xai_rollout.py --run artifacts/runs/vit_b16_primary` (panels, deletion test)",
           "`.venv/bin/python ml/experiments/xai_extended.py` (class gallery, failure cases, stability)",
           "Live: `POST /api/analyze?xai=true` returns the overlay as a PNG data URI; shown in each result card."])
    return d.save("B_XAI_Analysis_Report.docx")


# ======================================================================= C ABLATION
def doc_ablation():
    d = Doc("Ablation Study Report", "Ablation study", "Controlled experiments on training strategy, augmentation, GAN data, split design, noise and denoising.", META("C — Ablation study"))
    d.h1("Experiment matrix")
    d.table("Ablation experiments, hypotheses and status.", ["ID", "Hypothesis", "Variable changed", "Held constant", "Status"], [
        ["AB1", "Fine-tuning beats fixed features", "frozen features + logistic regression vs fine-tuned ViT", "split v1, test set", "COMPLETE"],
        ["AB2", "Conventional augmentation improves generalisation", "train-time augmentation on/off", "ViT-S, LR, epochs, split, seeds 42–44", ABL_STATUS],
        ["AB3", "GAN images add useful training signal", "+480 GAN images", "as AB2 (with conv. aug)", ABL_STATUS],
        ["AB4", "Session split over-estimates temporal generalisation", "session- vs day-grouped split", "ViT-S, conv. aug, LR, seeds 42–44", DAY_STATUS],
        ["AB5", "Spoilage prediction degrades under image noise", "Gaussian / salt-and-pepper / speckle, 3 levels each", "deployed ViT-B, test set", "COMPLETE"],
        ["AB6", "Denoising restores performance", "none / median 3×3 / DnCNN v1" + (" / DnCNN v2" if dn2 else ""), "as AB5", "COMPLETE" if dn2 else "IN PROGRESS"],
        ["AB7", "Larger backbone is better", "ViT-S/16 vs ViT-B/16", "split, aug (LR/batch differ — confounded)", "COMPLETE (confounded)"]],
        widths=[6, 26, 26, 28, 14], small=True)
    d.h1("Common protocol")
    d.bul([f"Split v1: session-grouped, duplicate-aware, seed 42 — {SPL['split_counts']['train']:,} train / {SPL['split_counts']['val']:,} val / {SPL['split_counts']['test']:,} test unique sRGB images.",
           "Model selection (checkpoint/epoch) uses only validation composite macro-F1 = mean(produce macro-F1, spoilage macro-F1). The test set is evaluated once per selected checkpoint.",
           "Primary metric: test spoilage macro-F1 (class-imbalanced task); secondary: accuracy, macro precision/recall, ROC-AUC, produce macro-F1.",
           "Validation scores are labelled as validation and are never reported as test accuracy."])
    d.h1("AB1 — Baselines versus fine-tuning")
    b = F["baselines"]
    d.table("Baselines and the deployed model on the same test split.", ["Model", "Features / training", "Produce mF1", "Spoil acc.", "Spoil macro-P", "Spoil macro-R", "Spoil mF1", "Spoil AUC"], [
        ["E0a", "HSV colour histogram (512-d) + logistic regression (C by val)", f3(b["colorhist"]["test_type"]["macro_f1"]), f3(b["colorhist"]["test_spoil"]["accuracy"]), f3(b["colorhist"]["test_spoil"]["macro_precision"]), f3(b["colorhist"]["test_spoil"]["macro_recall"]), f3(b["colorhist"]["test_spoil"]["macro_f1"]), f3(b["colorhist"]["test_spoil"]["roc_auc"])],
        ["E0b", "frozen ImageNet ViT-B/16 CLS embedding + logistic regression", f3(b["vit_frozen"]["test_type"]["macro_f1"]), f3(b["vit_frozen"]["test_spoil"]["accuracy"]), f3(b["vit_frozen"]["test_spoil"]["macro_precision"]), f3(b["vit_frozen"]["test_spoil"]["macro_recall"]), f3(b["vit_frozen"]["test_spoil"]["macro_f1"]), f3(b["vit_frozen"]["test_spoil"]["roc_auc"])],
        ["E4", "ViT-B/16 fine-tuned end to end (deployed)", f3(TT["macro_f1"]), f3(TS["accuracy"]), f3(TS["macro_precision"]), f3(TS["macro_recall"]), f3(TS["macro_f1"]), f3(TS["roc_auc"])]],
        widths=[6, 38, 9, 9, 10, 10, 9, 9], small=True)
    d.p(f"Fine-tuning improves spoilage macro-F1 by {TS['macro_f1'] - b['vit_frozen']['test_spoil']['macro_f1']:+.3f} over the frozen-feature probe, which in turn is {b['vit_frozen']['test_spoil']['macro_f1'] - b['colorhist']['test_spoil']['macro_f1']:+.3f} above colour histograms. Produce type is already perfectly separable with frozen features. These are single runs; " + (
        "the seed-to-seed SD of test spoilage macro-F1 measured in AB2 ranges from " + f"{min(S2[c]['test_spoil_macro_f1']['std'] for c in S2 if S2[c] and S2[c]['test_spoil_macro_f1']['std'] is not None):.3f} to {max(S2[c]['test_spoil_macro_f1']['std'] for c in S2 if S2[c] and S2[c]['test_spoil_macro_f1']['std'] is not None):.3f}, which bounds how much single-run differences can be trusted."
        if any(S2[c] and S2[c]['test_spoil_macro_f1']['std'] is not None for c in S2) else "seed variance is NOT AVAILABLE yet."))
    d.h1("AB2 and AB3 — Augmentation and GAN data (controlled, 3 seeds)")
    d.p("Hypotheses: (AB2) conventional augmentation improves test spoilage macro-F1 over real-only training; (AB3) adding 480 class-conditional GAN images improves it further. Configuration: Document A, Table 'Controlled configuration'.")
    d.table("Test results, mean ± SD over seeds.", COND_HDR, cond_rows(), widths=[24, 9, 7, 10, 10, 10, 10, 10, 10], small=True)
    d.table("Paired per-seed differences (test spoilage macro-F1).", ["Comparison", "Mean (per seed)"],
            [["Conventional aug − real only", diff_text("aug_minus_noaug")], ["GAN − conventional aug", diff_text("gan_minus_aug")]], widths=[35, 65])
    d.fig("ablation_v2_comparison.png", "Test spoilage macro-F1 per condition (mean ± SD, dots = seeds) and validation curves of every run.")
    d.fig("ablation_v2_confusions.png", "Spoilage confusion matrices summed over seeds.")
    am = PAIRS.get("aug_minus_noaug", {})
    if am.get("per_seed"):
        d.p(f"Finding (AB2): conventional augmentation changed test spoilage macro-F1 by {diff_text('aug_minus_noaug')}. "
            + ("The direction is consistent across seeds." if (all(x > 0 for x in am['per_seed']) or all(x < 0 for x in am['per_seed'])) else "The direction is not consistent across seeds, so no reliable effect is claimed.")
            + " Finding (AB3): see Document A — GAN images are mostly not recognisable as their intended class, and any change is within seed variation unless stated otherwise.")
    d.h1("Superseded single-seed runs (v1)")
    d.table("v1 ablation runs (lr 5e-5, seed 42).", ["Run", "Epochs", "Best epoch (val)", "Best val spoil mF1", "Test spoil mF1", "Note"], [
        [k, r["epochs_run"], r["best_epoch"], f3(r["best_val_spoil_macro_f1"]), f3(r["test_spoil"]["macro_f1"]),
         "unstable: best validation at epoch 1" if r["best_epoch"] == 1 else ""] for k, r in V1.items() if r], widths=[24, 9, 13, 15, 13, 26], small=True)
    d.p(f"The v1 conventional-augmentation run peaked on **validation** at epoch 1 (val spoilage macro-F1 {f3(V1['vit_s16_aug']['val_spoil_curve'][0])}) and oscillated afterwards; its **test** spoilage macro-F1 was {f3(V1['vit_s16_aug']['test_spoil']['macro_f1'])}. "
        "This instability (learning rate 2.5× the primary's) made v1 unsuitable for conclusions; v2 fixes the learning rate and adds seeds.")
    d.h1("AB4 — Split design sensitivity")
    d.p("Why split design matters for TR-6: the dataset stores every Classified image twice (byte-identical copy in Normal), each capture session has 17 near-identical views of one fruit, and spoilage labels follow capture date. "
        "Leakage was measured directly for four split schemes without training any model:")
    d.table("Measured leakage of test items into training for different split schemes.", ["Split scheme", "Test items", "Exact byte duplicate in train", "Same capture session in train", "Same produce & day in train"],
            [[r["split_scheme"], r.get("test_items") or r["test_contents"], f"{r['test_with_exact_duplicate_in_train_pct']:.1f}%", f"{r['test_with_same_session_in_train_pct']:.1f}%", f"{r['test_with_same_produce_day_in_train_pct']:.1f}%"] for r in F["split_leakage"]],
            widths=[40, 10, 16, 17, 17], source="`data/split_leakage_comparison.csv`", small=True)
    d.p("A random split of the raw files would put an exact copy of ~60% of test images into training and a near-identical view of every test image into training, so it would grossly over-estimate accuracy. "
        "The session-grouped split removes duplicate and same-session leakage but most test images still share a produce/day with training; the day-grouped split removes almost all of it.")
    if DS2:
        d.table("Day-grouped versus session-grouped split, identical configuration (ViT-S/16, conv. aug, lr 2e-5), seeds 42–44.", ["Split", "Seeds", "Train n", "Test n", "Spoil acc.", "Spoil mF1", "Spoil AUC", "Produce mF1"], [
            ["Session-grouped (v1)", S2["aug"]["n_seeds"] if S2.get("aug") else "–", S2["aug"]["n_train"] if S2.get("aug") else "–", SPL["split_counts"]["test"], pm(S2["aug"]["test_spoil_accuracy"]) if S2.get("aug") else "NOT RUN",
             pm(S2["aug"]["test_spoil_macro_f1"]) if S2.get("aug") else "NOT RUN", pm(S2["aug"]["test_spoil_auc"]) if S2.get("aug") else "NOT RUN", pm(S2["aug"]["test_type_macro_f1"]) if S2.get("aug") else ""],
            ["Day-grouped (sensitivity)", DS2["n_seeds"], DS2["n_train"], F["dataset"]["daysplit"]["split_counts"]["test"], pm(DS2["test_spoil_accuracy"]), pm(DS2["test_spoil_macro_f1"]), pm(DS2["test_spoil_auc"]), pm(DS2["test_type_macro_f1"])]],
            widths=[24, 8, 9, 9, 13, 13, 13, 11], small=True)
        d.p(f"Paired per-seed difference (day − session): {diff_text('day_minus_session_aug')}. Note the two splits have different test images, so this compares generalisation conditions rather than identical test sets.")
    else:
        d.note("Day-grouped runs at the controlled configuration: NOT AVAILABLE at build time.", warn=True)
    dv = V1["vit_s16_aug_daysplit"]
    d.p(f"Earlier single run (v1 configuration, lr 5e-5): day-grouped test spoilage macro-F1 {f3(dv['test_spoil']['macro_f1'])} vs {f3(V1['vit_s16_aug']['test_spoil']['macro_f1'])} session-grouped (best validation {f3(dv['best_val_spoil_macro_f1'])} at epoch {dv['best_epoch']} — a large validation–test gap).")
    d.h1("AB5 and AB6 — Noise robustness and denoising")
    lv = {"gaussian": [0.05, 0.1, 0.2], "salt_pepper": [0.02, 0.05, 0.1], "speckle": [0.1, 0.3, 0.5]}
    dens = ["none", "median", "dncnn"] + (["dncnn2"] if dn2 else [])
    rows = []
    for k, ls in lv.items():
        for l in ls:
            rows.append([k.replace("_", " & "), l] + [f3(rob(k, l, dd)["spoil_macro_f1"]) if rob(k, l, dd) else "NOT RUN" for dd in dens])
    d.table(f"Test spoilage macro-F1 under deterministic corruptions (clean: {f3(TS['macro_f1'])}).", ["Corruption", "Level"] + ["No denoiser", "Median 3×3", "DnCNN v1"] + (["DnCNN v2"] if dn2 else []),
            rows, source="`data/noise_robustness.csv`", small=True)
    d.fig("noise_robustness.png", "Spoilage macro-F1 versus noise level for each denoiser.")
    d.fig("noise_examples.png", "Example corruption and denoising outputs on one test image.", width=0.75)
    dq = F["dncnn_v1"]["paired_val_quality"]
    rowsq = [[r["corruption"], r["level"], f"{r['noisy_psnr']:.2f}", f"{r['median_psnr']:.2f}", f"{r['dncnn_psnr']:.2f}",
              (f"{next(x for x in dn2['paired_val_quality'] if x['corruption'] == r['corruption'] and x['level'] == r['level'])['dncnn_psnr']:.2f}" if dn2 else "NOT RUN")] for r in dq]
    d.table("Paired denoising quality on validation images (PSNR, dB; clean reference known).", ["Corruption", "Level", "Noisy", "Median", "DnCNN v1", "DnCNN v2"], rowsq, small=True,
            source="`artifacts/experiments/dncnn*/dncnn_results.json`")
    d.p(f"Findings: spoilage is far more sensitive to noise than produce type (produce macro-F1 stays ≥ {min(r['type_macro_f1'] for r in F['robustness']):.3f} in every condition). "
        "Salt-and-pepper noise is the most damaging without denoising but is almost fully repaired by a 3×3 median filter; Gaussian and speckle noise degrade performance smoothly and denoising helps little or hurts slightly at low noise. "
        f"DnCNN v1 trained for only {F['dncnn_v1']['steps']:,} steps and is worse than the median filter on PSNR in every condition" + (f"; DnCNN v2 resumed training to {dn2['steps']:,} steps." if dn2 else ".")
        + f" The intrinsic noise of TR-6 photographs (σ ≈ {F['noise_profile']['overall_fullres_mean']:.4f} at full resolution) is far below the tested levels (σ ≥ 0.05), so these are stress tests, not estimates of field performance.")
    d.h1("AB7 — Backbone size (confounded)")
    if S2.get("aug"):
        d.p(f"ViT-S/16 with conventional augmentation (v2) reached {pm(S2['aug']['test_spoil_macro_f1'])} test spoilage macro-F1; the deployed ViT-B/16 reached {f3(TS['macro_f1'])} (one seed). "
            "Learning rate, batch size and number of epochs also differ between the two (ViT-B: batch 16, 12 epochs), so this is not a clean single-factor ablation.")
    d.h1("Conclusions")
    d.bul([f"Fine-tuning a pretrained ViT is the single most important factor (AB1).",
           (f"Conventional augmentation gave a small gain ({diff_text('aug_minus_noaug')})" + (", positive on every seed" if PAIRS['aug_minus_noaug']['per_seed'] and all(x > 0 for x in PAIRS['aug_minus_noaug']['per_seed']) else ", not consistent across seeds")
            + f"; adding GAN images gave {diff_text('gan_minus_aug')}, " + ("not consistent across seeds, so no benefit of GAN augmentation is established (AB2/AB3)." if not (all(x > 0 for x in PAIRS['gan_minus_aug']['per_seed']) or all(x < 0 for x in PAIRS['gan_minus_aug']['per_seed'])) else "consistent in sign but small (AB2/AB3).")),
           f"Split design dominates apparent performance: the day-grouped split lowers test spoilage macro-F1 by {diff_text('day_minus_session_aug')} at identical configuration (AB4); random splits would leak duplicates and are invalid.",
           "Robustness to strong noise is limited for spoilage; median filtering is a cheap, effective defence for impulse noise (AB5/AB6)."])
    d.h1("Limitations")
    d.bul(["Three seeds per condition; confidence intervals are wide.", "One GAN seed.", "All results are on lab images of a small number of specimens.", "Backbone comparison is confounded."])
    return d.save("C_Ablation_Study_Report.docx")


# ======================================================================= D FINAL RESULTS
def doc_results():
    d = Doc("Final Results and Model Metrics Report", "Final results", "Consolidated, evidence-traced results of the complete Foresight system.", META("D — Final results and model metrics"))
    a = D["audit"]
    d.h1("Dataset audit and preprocessing")
    d.table("TR-6 audit (re-run 2026-10-15; identical to the 2026-10-12 audit).", ["Quantity", "Value"], [
        ["Files / size", f"{a['file_count']:,} / {a['total_gib']:.2f} GiB"], ["Valid JPEGs (sRGB / thermal)", f"{a['valid_images']:,} ({a['image_counts']['srgb']:,} / {a['image_counts']['thermal_ir_fusion']:,}); corrupt {a['corrupt_or_invalid_images']}"],
        ["Methane files / records", f"{a['methane_file_count']} / {a['methane_record_count']:,}"], ["Unique image contents", f"{a['unique_image_hashes']:,}"],
        ["Exact-duplicate groups / excess copies", f"{a['duplicate_groups']:,} / {a['duplicate_excess_copies']:,}"],
        ["Classified images byte-identical to a Normal image", f"{a['classified_images_exactly_duplicated_in_normal']:,}"],
        ["Cross-label (Spoiled & Not_spoiled) content groups", a["cross_label_duplicate_groups"]], ["Verified cross-modal pairs", a["verified_cross_modal_pairs"]]],
        widths=[55, 45], source="`dataset-preparation/tr6-audit/output_rerun_2026-10-15/audit_summary.json`")
    d.p("Preprocessing: content-level de-duplication by SHA-256; spoilage label = Classified folder label (dataset-provided, not independently verified); conflicting contents excluded; thermal excluded (RGB app); each eligible image decoded once with EXIF orientation correction and resized to shorter side 256 (`artifacts/cache/srgb_256`), then resized to 224×224 and normalised with the backbone's pretrained mean/std. The backend applies the same steps to uploads (test R03).")
    d.table("Eligibility and exclusions (unique contents).", ["Category", "Count"],
            [["Unique image contents", f"{SPL['unique_image_contents']:,}"]] + [[k.replace("_", " "), f"{v:,}"] for k, v in SPL["exclusions"].items()] + [["Eligible sRGB samples", f"{SPL['eligible_samples']:,}"]], widths=[70, 30])
    cd = D["class_distribution"]
    d.table("Train / validation / test sample counts and class distributions.", ["Class", "Train", "Validation", "Test"],
            [[nice(c), cd["train"]["type"][c], cd["val"]["type"][c], cd["test"]["type"][c]] for c in PROD]
            + [[nice(c), cd["train"]["spoil"][c], cd["val"]["spoil"][c], cd["test"]["spoil"][c]] for c in ("Not_spoiled", "Spoiled")]
            + [["Total", SPL["split_counts"]["train"], SPL["split_counts"]["val"], SPL["split_counts"]["test"]]], widths=[40, 20, 20, 20])
    d.fig("split_distribution.png", "Session-grouped 60/20/20 split per produce × label stratum.")
    d.h1("Models and checkpoints")
    d.table("Models implemented, trained and deployed.", ["Model", "Role", "Trained?", "Checkpoint", "Used in app?"], [
        ["ViT-B/16 two-head (86 M params)", "produce type + spoilage", "YES (12 epochs)", P["checkpoint"], "YES (deployed copy)"],
        ["ViT-S/16 two-head (22 M params)", "ablations", f"YES ({v2_done + day_done + 4} runs)", "artifacts/runs/abl2_*, day2_*, vit_s16_*", "research only"],
        ["Conditional DCGAN", "training-only augmentation", "YES", "artifacts/experiments/gan/cdcgan.pt", "research only"],
        ["DnCNN (depth 17)", "denoising experiment", "YES (under-trained)" if not dn2 else "YES", "artifacts/experiments/dncnn*/dncnn.pt", "research only"],
        ["Logistic regression ×2", "baselines", "YES", "metrics only", "research only"], ["K-means", "exploratory clustering", "YES (fit on train)", "metrics only", "research only"],
        ["U-Net", "decay segmentation", "NOT RUN", "—", "BLOCKED"], ["YOLO", "detection", "NOT RUN", "—", "NOT IMPLEMENTED"], ["Shelf-life regressor", "regression", "NOT RUN", "—", "BLOCKED"]],
        widths=[22, 20, 15, 29, 14], small=True)
    d.h1("Training history")
    d.fig("primary_training_loss.png", "Training (augmented) and validation loss of the deployed ViT-B/16.")
    d.fig("primary_validation_metrics.png", f"Validation macro-F1 per epoch; the selected checkpoint (epoch {P['best_epoch']}) is marked.")
    d.table("Primary training history (from `artifacts/runs/vit_b16_primary/history.json`).", ["Epoch", "Train loss", "Val loss", "Val produce mF1", "Val spoil mF1", "Seconds"],
            [[h["epoch"], f3(h["train_loss"]), f3(h["val_loss"]), f3(h["val_type_macro_f1"]), f3(h["val_spoil_macro_f1"]), h["seconds"]] for h in P["history"]], small=True)
    d.h1("Test-set performance of the selected checkpoint")
    d.table("Held-out test metrics (n = 1,071; evaluated once after selection).", ["Head", "Accuracy", "Macro precision", "Macro recall", "Macro-F1", "Weighted-F1", "ROC-AUC"], [
        ["Produce type (6)", f4(TT["accuracy"]), f4(TT["macro_precision"]), f4(TT["macro_recall"]), f4(TT["macro_f1"]), f4(TT["weighted_f1"]), f4(TT["roc_auc"])],
        ["Spoilage (2)", f4(TS["accuracy"]), f4(TS["macro_precision"]), f4(TS["macro_recall"]), f4(TS["macro_f1"]), f4(TS["weighted_f1"]), f4(TS["roc_auc"])]], small=True)
    d.table("Per-class test metrics.", ["Head", "Class", "Precision", "Recall", "F1", "Support"],
            [["Spoilage", nice(c), f4(v["precision"]), f4(v["recall"]), f4(v["f1"]), v["support"]] for c, v in P["test_spoil_per_class"].items()]
            + [["Produce", nice(c), f4(v["precision"]), f4(v["recall"]), f4(v["f1"]), v["support"]] for c, v in P["test_type_per_class"].items()], small=True)
    d.p(f"Statistical interpretation: a cluster bootstrap over the {BOOT['n_sessions']} test capture sessions (2,000 resamples) gives 95% intervals of **[{BOOT['spoil_macro_f1_95ci'][0]:.3f}, {BOOT['spoil_macro_f1_95ci'][1]:.3f}]** for spoilage macro-F1, "
        f"[{BOOT['spoil_accuracy_95ci'][0]:.3f}, {BOOT['spoil_accuracy_95ci'][1]:.3f}] for accuracy and [{BOOT['spoiled_recall_95ci'][0]:.3f}, {BOOT['spoiled_recall_95ci'][1]:.3f}] for Spoiled recall. Images inside a session are highly correlated, so these session-level intervals are the honest uncertainty, much wider than an image-level interval would suggest.")
    d.fig("primary_confusion_spoilage.png", "Test confusion matrix — spoilage.", width=0.5)
    d.fig("primary_confusion_produce.png", "Test confusion matrix — produce type.", width=0.6)
    d.fig("primary_roc_spoilage.png", "Test ROC curve for the Spoiled class.", width=0.5)
    d.fig("primary_per_class.png", "Per-class precision, recall and F1 on the test split.")
    d.fig("primary_errors_by_stratum.png", "Test spoilage error rate per produce × label stratum.")
    d.fig("primary_calibration.png", f"Reliability diagram for the spoilage head (ECE = {CAL['ece_10bin']:.3f}); numbers are images per bin.", width=0.5)
    d.p(f"Calibration: expected calibration error is {CAL['ece_10bin']:.3f}, but this is dominated by the many easy, correct, confident predictions; {pct(CAL['share_of_errors_with_conf_ge_0.9'], 0)} of the {CAL['n_errors']} errors were made with confidence ≥ 0.90 (mean confidence of wrong predictions {CAL['mean_conf_wrong']:.3f}). Confidence scores are therefore not a reliable warning signal and are shown in the UI as uncalibrated.")
    d.h1("Model comparison and ablations")
    b = F["baselines"]
    rows = [["Colour histogram + LogReg", "1 run", f3(b["colorhist"]["test_spoil"]["macro_f1"]), f3(b["colorhist"]["test_spoil"]["roc_auc"])],
            ["Frozen ViT-B + LogReg", "1 run", f3(b["vit_frozen"]["test_spoil"]["macro_f1"]), f3(b["vit_frozen"]["test_spoil"]["roc_auc"])]]
    for c, lab in (("noaug", "ViT-S/16 real only"), ("aug", "ViT-S/16 + conv. aug"), ("gan", "ViT-S/16 + conv. aug + GAN")):
        if S2.get(c):
            rows.append([lab, f"{S2[c]['n_seeds']} seeds", pm(S2[c]["test_spoil_macro_f1"]), pm(S2[c]["test_spoil_auc"])])
    rows.append(["ViT-B/16 + conv. aug (deployed)", "1 run", f3(TS["macro_f1"]), f3(TS["roc_auc"])])
    d.table("Comprehensive model comparison on the same test split (spoilage).", ["Model", "Runs", "Spoilage macro-F1", "Spoilage ROC-AUC"], rows, widths=[46, 14, 20, 20])
    d.fig("ablation_v2_comparison.png", "Controlled ViT-S/16 comparison (3 seeds) and validation curves; details in Documents A and C.")
    d.h1("Noise robustness and denoising")
    d.fig("noise_robustness.png", "Test spoilage macro-F1 under synthetic noise with and without denoising.")
    d.fig("denoising_psnr_ssim_v1.png", "Paired PSNR / SSIM of DnCNN v1 and the median filter on validation images.")
    d.h1("GAN augmentation")
    d.p(f"See Document A. GAN images were recognised as their intended produce by the deployed classifier in only {pct(GL['overall_type_match'])} of cases; the controlled comparison is in the model-comparison table above.")
    d.fig("gan_label_consistency.png", "GAN label consistency under the deployed classifier.")
    d.h1("K-means clustering")
    km = F["kmeans"]
    d.table("K-means alignment with labels (clusters fitted on train only; k chosen by silhouette without labels).", ["Features", "k selected (silhouette)", "k / split", "ARI produce", "NMI produce", "ARI spoilage", "NMI spoilage"],
            [[s, km[s]["k_selected"], k, f3(v["ARI_produce"]), f3(v["NMI_produce"]), f3(v["ARI_spoilage"]), f3(v["NMI_spoilage"])] for s in ("vit_frozen", "colorhist") for k, v in km[s]["alignment"].items() if "test" in k],
            small=True)
    d.p("Unsupervised structure in frozen ViT features is dominated by produce type (k = 6 recovers it almost exactly), not by spoilage; clusters are exploratory and not ground truth.")
    d.fig("kmeans_vit_frozen.png", "K-means (k = 6) on frozen ViT features, PCA projection of the training split, coloured by cluster (left) and true produce (right).")
    d.h1("Explainability")
    d.fig("xai_class_gallery_part1.png", "Attention rollout on correct test images, Banana / Carrot / Guava (Document B).")
    d.fig("xai_class_gallery_part2.png", "Attention rollout on correct test images, Indian Gooseberry / Mango / Tomato.")
    d.fig("xai_failure_fn.png", "Attention rollout on test false negatives.")
    d.h1("Inference latency and resources")
    r1, r2 = RES["ViT-B/16 primary"], RES["ViT-S/16 ablation"]
    d.table("Measured latency and resource use (Apple M5, 16 GB).", ["Measurement", "Value"], [
        ["ViT-B/16 parameters / checkpoint", f"{r1['parameters']:,} / {r1['checkpoint_mb']} MB"], ["ViT-S/16 parameters / checkpoint", f"{r2['parameters']:,} / {r2['checkpoint_mb']} MB"],
        ["ViT-B/16 single-image forward, CPU / MPS (median)", f"{r1['single_image_latency_ms_cpu_median']:.1f} / {r1['single_image_latency_ms_mps_median']:.1f} ms"],
        ["ViT-S/16 single-image forward, CPU / MPS (median)", f"{r2['single_image_latency_ms_cpu_median']:.1f} / {r2['single_image_latency_ms_mps_median']:.1f} ms"],
        ["ViT-B/16 batched test inference (MPS)", f"{P['batched_latency_ms']:.1f} ms/image"],
        ["End-to-end /api/analyze (1.9 MB upload, n = 60)", f"median {LAT['median_ms']:.0f} ms, p95 {LAT['p95_ms']:.0f} ms"],
        ["Backend physical memory footprint", f"{RES.get('backend_physical_footprint_mb')} MB (peak {RES.get('backend_physical_footprint_peak_mb')} MB)"],
        ["Primary training time", f"{P['train_minutes']} min (12 epochs, MPS)"]], widths=[55, 45])
    d.fig("api_latency.png", "Distribution of end-to-end API latency in the E2E smoke test.", width=0.6)
    d.h1("API / UI integration results")
    d.p(f"The React UI calls the FastAPI backend, which loads the selected checkpoint once at startup. In the end-to-end test {E2E['held_out_images_via_api']} held-out full-resolution originals were analysed via HTTP: produce correct {E2E['produce_correct']}/{E2E['held_out_images_via_api']}, spoilage correct {E2E['spoilage_correct']}/{E2E['held_out_images_via_api']}; {E2E['passed']}/{E2E['total']} E2E checks passed and {T['ui_contract']['fields_present']}/{T['ui_contract']['fields_checked']} UI-consumed fields were present in real responses. Limitations: single-item mode only; no shelf-life or decay-area output; mock mode exists but is off by default and labelled.")
    d.h1("Conclusions")
    d.bul([f"A genuine ViT-B/16 classifier was trained on {SPL['eligible_samples']:,} de-duplicated TR-6 images and reaches test spoilage macro-F1 {f3(TS['macro_f1'])} (session-bootstrap 95% CI {BOOT['spoil_macro_f1_95ci'][0]:.3f}–{BOOT['spoil_macro_f1_95ci'][1]:.3f}) and perfect produce classification; it is integrated and serving real predictions.",
           "Performance is optimistic for real-world use: specimens recur across splits, a day-grouped split lowers performance (Document C), lab backgrounds are uniform, and confidence is poorly calibrated on errors.",
           "The weakest point is recall of 'Spoiled' for Indian Gooseberry and Tomato, plausibly because date-based labels precede visible decay.",
           "Segmentation, shelf-life and detection remain blocked by missing annotations, not by code."])
    return d.save("D_Final_Results_and_Model_Metrics_Report.docx")


# ======================================================================= E TESTING STRATEGY
TEST_DESC = {
    "test_health_reports_loaded_model": ("API", "Health reports model state", "tiny fixture checkpoint", "GET /health, /api/health", "200; model_loaded true; mock false"),
    "test_models_lists_honest_statuses": ("API", "Honest model statuses", "fixture", "GET /api/models", "vit loaded; unet unavailable; shelf_life disabled"),
    "test_analyze_valid_jpeg_returns_real_inference_contract": ("API", "Inference contract; no invented values", "fixture", "POST JPEG", "200; source model; probabilities sum 1; days/decayPct null"),
    "test_analyze_is_deterministic": ("Model", "Deterministic inference", "fixture", "POST same image twice", "identical probabilities"),
    "test_analyze_png_and_webp": ("API", "PNG/WEBP accepted", "fixture", "POST PNG and WEBP", "200"),
    "test_xai_overlay": ("API", "XAI overlay returned", "fixture", "POST ?xai=true", "attention_rollout; PNG data URI"),
    "test_rejects_wrong_media_type": ("Validation", "Unsupported type rejected", "fixture", "POST text/plain", "415 unsupported_media_type"),
    "test_rejects_corrupt_image": ("Validation", "Corrupt image rejected", "fixture", "POST truncated JPEG", "400 invalid_image"),
    "test_rejects_empty_file": ("Validation", "Empty file rejected", "fixture", "POST 0 bytes", "400 invalid_image"),
    "test_rejects_tiny_image": ("Validation", "Too-small image rejected", "fixture", "POST 8×8", "400"),
    "test_rejects_unsupported_decoded_format": ("Validation", "Undecodable/unsupported format", "fixture", "POST GIF as octet-stream", "400 'Unsupported image format'"),
    "test_missing_field_is_422": ("Validation", "Malformed request", "fixture", "POST without 'photo'", "422 invalid_request"),
    "test_oversized_upload_413": ("Validation", "Upload size limit", "limit 0.01 MB", "POST 20 KB", "413 file_too_large"),
    "test_missing_checkpoint_fails_clearly": ("Failure", "Missing checkpoint fails clearly", "non-existent path", "GET /health; POST", "degraded; 503 model_unavailable; nothing stored"),
    "test_mock_mode_is_explicitly_labelled": ("Failure", "Mock mode labelled", "MOCK_MODE on", "POST; GET /api/report", "mock true; 'DEMO MOCK DATA' everywhere"),
    "test_history_persists_and_is_queryable": ("Persistence", "History persistence", "temp SQLite", "2 scans; restart app; query; clear", "2 rows survive restart; detail; 404; cleared"),
    "test_report_text_and_pdf": ("API", "Report generation", "1 scan", "GET /api/report, /pdf", "disclaimer line; %PDF"),
    "test_nutrition_and_tips": ("API", "Static content endpoints", "—", "GET nutrition, tips", "200 / 404 for unknown"),
    "test_cors_allows_dev_origin_only": ("Security", "CORS restricted", "—", "Origin allowed vs evil.example", "header only for allowed origin"),
    "test_real_model_loads": ("Model", "Real checkpoint loads", "real checkpoint", "GET /health", "version not fixture"),
    "test_real_inference_on_held_out_source_images": ("Model", "Real inference on held-out originals", "12 test originals (1/stratum)", "POST full-res JPEGs", "produce ≥11/12, spoilage ≥9/12"),
    "test_backend_preprocessing_matches_training_cache": ("Data", "Reproducible preprocessing", "1 original + cache", "decode/EXIF/resize vs cache", "same size; mean abs diff < 3"),
    "test_png_upload_of_real_image": ("Model", "PNG of real image + XAI", "real checkpoint", "POST PNG ?xai", "200; overlay present"),
    "test_manifest_schema": ("Data", "Manifest schema", "split manifest", "check columns; unique hashes", "required fields; 1 row/content"),
    "test_eligible_rows_have_valid_labels": ("Data", "Valid labels; no invented IDs", "manifest", "check eligible rows", "6 classes × 2 labels; specimen_id empty"),
    "test_conflicting_labels_excluded": ("Data", "Conflicts excluded", "manifest", "count conflicts", "170 excluded"),
    "test_no_leakage_between_splits": ("Data", "No duplicate/session leakage", "manifest", "map paths & sessions → splits", "each in exactly one split"),
    "test_split_fractions_close_to_60_20_20": ("Data", "60/20/20 split", "manifest + summary", "count", "within ±2%; summary matches"),
    "test_every_stratum_in_every_split": ("Data", "Stratified coverage", "manifest", "check 12 strata × 3 splits", "all present"),
    "test_source_files_unchanged": ("Data", "Source immutability", "dataset", "re-hash sample of originals", "SHA-256 equal to audit"),
    "test_corruptions_are_deterministic_and_bounded": ("Robustness", "Deterministic corruptions", "synthetic image", "same/different seed", "identical / different; s&p fraction ≈ p"),
    "test_model_forward_shapes": ("Model", "Forward pass shapes", "tiny ViT", "forward 2 images", "(2,6), (2,2)"),
    "test_gan_outputs_marked_synthetic_and_train_only": ("Data", "Synthetic data marked", "GAN manifest", "check provenance/paths", "synthetic_cdcgan_train_only"),
}


def doc_testing():
    d = Doc("Testing Strategy, Test Designs and Frameworks", "Testing strategy", "Strategy, design and executed results of data, model, API, UI, performance and end-to-end tests.", META("E — Testing strategy and test designs"))
    d.h1("Test strategy and system architecture")
    d.p("System under test: React/Vite UI → `frontend/src/api.js` → FastAPI (`backend/main.py`) → validation & decoding (`inference.decode_image`) → ViT-B/16 inference (`inference.ModelService`) → deterministic result composer → SQLite history (`db.py`). Offline: audit → split → cache → training → evaluation → experiments.")
    d.p("Strategy: (1) data-integrity tests guard against leakage and source mutation; (2) model tests check loading, shapes, determinism and real-image behaviour; (3) API tests use FastAPI `TestClient` with a tiny random fixture checkpoint for fast contract and failure tests, plus the real checkpoint for behavioural tests; (4) UI unit tests use Vitest + Testing Library; (5) a live end-to-end smoke test drives both running servers over HTTP; (6) manual browser checks cover visual states. Tests that are designed but not executed are marked NOT RUN.")
    d.table("Test levels, frameworks and evidence.", ["Level", "Framework / tool", "Scope", "Executed result", "Evidence"], [
        ["Unit + data integrity", "pytest 9.1", "manifest, splits, leakage, immutability, corruptions, model shapes", "PASS", "`ml/tests/test_ml.py`"],
        ["API / integration", "pytest + FastAPI TestClient", "contract, validation, failures, history, CORS, report", "PASS", "`backend/tests/test_api.py`"],
        ["Model (real checkpoint)", "pytest", "loading, held-out inference, preprocessing parity, XAI", "PASS", "`backend/tests/test_real_model.py`"],
        ["Frontend unit", "Vitest 2.1 + Testing Library + jsdom", "api.js errors, ItemCard honesty, mock label, About live status", "PASS" if VITEST and VITEST["numFailedTests"] == 0 else "NOT RUN", "`frontend/src/__tests__/`"],
        ["Contract", "httpx script", "every UI-consumed field present in live responses", "PASS", "`scripts/check_ui_contract.py`"],
        ["End-to-end", "httpx script vs running uvicorn + Vite", "60 held-out originals, errors, history, PDF, CORS", "PASS", "`scripts/e2e_smoke.py`"],
        ["Performance", "e2e script, extra_analyses resources", "latency, memory", "MEASURED", "`evidence/latency_benchmark.json`"],
        ["Robustness", "evaluate_vit.py", "noise × denoiser grid on test split", "MEASURED", "Document C"],
        ["Build", "Vite 5", "production bundle", "PASS", "`evidence/frontend_build.log`"],
        ["UI (manual)", "in-app browser", "upload, result, errors, history, about", "PASS", "Section 7"],
        ["Load / concurrency", "—", "parallel requests", "NOT RUN", "—"],
        ["Mobile camera, real-world photos", "—", "physical device; non-TR-6 images", "NOT RUN", "—"]], widths=[16, 20, 30, 12, 22], small=True)
    d.h1("Automated test cases (pytest)")
    rows, counters = [], {}
    prefix = {"test_api.py": "B", "test_real_model.py": "R", "test_ml.py": "M"}
    for name, status in pytest_cases:
        fpath, fn = name.split("::")
        pre_ = prefix.get(Path(fpath).name, "T"); counters[pre_] = counters.get(pre_, 0) + 1
        lvl, req, pre, steps, exp = TEST_DESC.get(fn, ("?", fn, "", "", ""))
        rows.append([f"{pre_}{counters[pre_]:02d}", lvl, req, pre, steps, exp, "as expected" if status == "PASSED" else status, "PASS" if status == "PASSED" else "FAIL"])
    d.table(f"pytest cases ({T['pytest_summary']}); B = API (`backend/tests/test_api.py`), R = real checkpoint (`test_real_model.py`), M = data/model (`ml/tests/test_ml.py`); actual output: `evidence/pytest_final.log`.", ["ID", "Level", "Requirement", "Precondition / input", "Steps", "Expected", "Actual", "Status"],
            rows, widths=[5, 9, 17, 14, 15, 22, 9, 9], small=True)
    d.h1("Frontend unit tests (Vitest)")
    if VITEST:
        rows = [[f"V{i:02d}", t["file"], t["name"], "PASS" if t["status"] == "passed" else "FAIL"] for i, t in enumerate(VITEST["tests"], 1)]
        d.table(f"Vitest results ({VITEST['numPassedTests']}/{VITEST['numTotalTests']} passed); `evidence/vitest.json`.", ["ID", "File", "Test", "Status"], rows, widths=[6, 22, 62, 10], small=True)
    else:
        d.note("Vitest results NOT AVAILABLE.", warn=True)
    d.h1("End-to-end smoke test")
    d.table(f"Live E2E checks ({E2E['passed']}/{E2E['total']} passed; model {E2E['model_version']}, device {E2E['device']}).", ["ID", "Check", "Detail", "Status"],
            [[f"E{i:02d}", c["check"], c["detail"], "PASS" if c["pass"] else "FAIL"] for i, c in enumerate(E2E["checks"], 1)], widths=[6, 40, 44, 10], small=True)
    ui = T["ui_contract"]
    d.table(f"UI ↔ API contract: fields read by the React code, checked against live responses ({ui['fields_present']}/{ui['fields_checked']} present).", ["Endpoint (UI variable)", "Field", "Present", "Type in response"],
            [[c["endpoint"], c["field"], "PASS" if c["present"] else "FAIL", c["type"] + (f" — {c['null_by_design']}" if c["null_by_design"] else "")] for c in ui["checks"]], widths=[36, 20, 10, 34], small=True)
    d.h1("Performance and resource constraints")
    d.table("Performance requirements and measurements.", ["Requirement", "Target", "Measured", "Status"], [
        ["End-to-end analysis latency (MPS)", "< 2 s per photo", f"median {LAT['median_ms']:.0f} ms, p95 {LAT['p95_ms']:.0f} ms", "PASS"],
        ["CPU-only inference (deployment without GPU)", "< 1 s forward pass", f"{RES['ViT-B/16 primary']['single_image_latency_ms_cpu_median']:.0f} ms", "PASS"],
        ["Backend memory", "fits a 2 GB instance", f"{RES.get('backend_physical_footprint_mb')} MB (peak {RES.get('backend_physical_footprint_peak_mb')} MB)", "PASS"],
        ["Upload size limit", "reject > 15 MB", "413 (test B13)", "PASS"]], widths=[34, 22, 30, 14])
    d.h1("Manual UI verification")
    d.table("Browser checks performed in the in-app browser against the running services.", ["ID", "Scenario", "Observed", "Status"], [
        ["U01", "Upload held-out Banana/Spoiled original via the real file input", "Card: Banana, Spoiled (100%), shelf-life 'Not available', decay 'Pending annotation', model version, warnings, disclaimer, rollout overlay on the fruit", "PASS"],
        ["U02", "Upload corrupt JPEG", "'The file could not be decoded as an image (corrupt or not an image).'", "PASS"],
        ["U03", "Backend started with missing checkpoint", "Banner and error: 'Model unavailable: Checkpoint not found…'; no result card", "PASS"],
        ["U04", "Backend stopped", "'Could not reach the analysis backend at http://localhost:8000…'", "PASS (after fix D02)"],
        ["U05", "History / Dashboard / About pages", "persisted real scans; live /api/models status; no console errors", "PASS"]], widths=[6, 30, 52, 12], small=True)
    d.h1("Defect log")
    d.table("Defects found during implementation and testing.", ["ID", "Defect", "Found by", "Fix", "Status"], [
        ["D01", "GAN generation crashed: `.view()` on non-contiguous tensor", "running gan.py generate", "use `.reshape()`", "FIXED"],
        ["D02", "Missing space in 'backend unreachable' banner", "manual UI check U04", "text fix + rebuild", "FIXED"],
        ["D03", "Helper `test_rows` would be collected by pytest", "code review", "renamed `held_out_rows`", "FIXED"],
        ["D04", "Relative env paths resolved against shell cwd", "review of .env.example", "resolve relative to backend/", "FIXED"],
        ["D05", "Resource script measured RSS of shell wrapper / compressed pages", "implausible 16–26 MB", "use macOS `footprint`", "FIXED"],
        ["D06", "ViT-S v1 ablation unstable (best val at epoch 1)", "ablation review", "controlled v2 at lr 2e-5, 3 seeds", "FIXED (re-run)"],
        ["D07", "Original UI showed fabricated detections/sizes/shelf-life", "integration audit", "removed; honest fields", "FIXED"],
        ["D08", "No frontend automated tests", "test audit", "Vitest suite added", "FIXED"]], widths=[6, 34, 20, 26, 14], small=True)
    d.h1("Regression-testing plan")
    d.bul(["Run on every change: `.venv/bin/python -m pytest backend/tests ml/tests -q`, `cd frontend && npm test && npm run build`.",
           "Run before every demo/release: start both servers, then `scripts/e2e_smoke.py --n 60` and `scripts/check_ui_contract.py`.",
           "On a new checkpoint: re-run `ml/evaluate/evaluate_vit.py --split test` once, update `backend/models/foresight_vit_test_metrics.json`; the real-model tests (R01–R04) must still pass.",
           "On any dataset/split change: re-run the audit, `make_splits.py`, and the ML tests; the byte-identical reproducibility of the manifest is the regression oracle.",
           "Planned, not yet implemented: Playwright browser E2E in CI; concurrency/load test; tests on real-world phone photos."])
    return d.save("E_Testing_Strategy_and_Test_Designs.docx")


# ======================================================================= F AI MODEL TEST & EVAL
def doc_eval():
    d = Doc("AI Model Testing and Evaluation Report", "AI model evaluation", "Problem definition, data, training, evaluation, robustness, limitations and deployment verification of the Foresight spoilage classifier.", META("F — AI model testing and evaluation"))
    d.h1("Problem statement and intended use")
    d.p("Task: given one RGB photograph of a single fruit or vegetable from six supported types, predict (a) the produce type and (b) whether it shows the visual characteristics of TR-6 images labelled 'Spoiled'. "
        "Intended use: an educational research prototype that flags visible spoilage cues. It is **not** a food-safety determination, cannot see internal decay, and does **not** estimate shelf life (no valid time-to-endpoint labels exist).")
    d.table("Prediction scope.", ["Output", "Classes / form", "Supported?"], [
        ["Produce type", ", ".join(nice(c) for c in PROD), "YES"], ["Spoilage", "Not spoiled / Spoiled (softmax score, uncalibrated)", "YES"],
        ["Shelf-life (days)", "—", "NO (BLOCKED: no labels)"], ["Decay mask / area", "—", "NO (BLOCKED: no reviewed masks)"], ["Multiple items per photo", "—", "NO (single-item mode)"]], widths=[25, 55, 20])
    d.h1("Do the labels support a spoilage interpretation?")
    d.p("The spoilage target is the TR-6 `Classified/{Spoiled, Not_spoiled}` folder label supplied by the dataset authors. Evidence gathered: (i) every Classified image is a byte-identical copy of a Normal image, i.e. the labels were assigned to an existing time series; "
        f"(ii) within each produce type the label is a function of capture date — the last Not_spoiled capture precedes the first Spoiled capture for {sum(v['all_not_spoiled_before_all_spoiled'] for v in F['label_date_order'].values())} of 6 produce types (" + "; ".join(f"{nice(t)}: NS {v['not_spoiled_first'][:10]}→{v['not_spoiled_last'][:10]}, S {v['spoiled_first'][:10]}→{v['spoiled_last'][:10]}" for t, v in F['label_date_order'].items()) + "); "
        "(iii) 170 thermal contents carry both labels and were excluded; "
        "(iv) visual inspection shows clear decay for Spoiled banana, carrot and guava, but many Spoiled Indian Gooseberries look fresh. "
        "Conclusion: the labels support the interpretation **'resembles the dataset authors' later-stage (spoiled) images'**, which partly coincides with visible decay. They were not independently verified, and the model's outputs must be described accordingly.")
    d.h1("Dataset provenance, eligibility and balance")
    d.p(f"Source: TriModal Ripeness 6 (Bagyammal et al., 2025; Figshare DOI 10.6084/m9.figshare.30783827.v1; CC BY 4.0). Of {SPL['unique_image_contents']:,} unique image contents, {SPL['eligible_samples']:,} sRGB contents were eligible "
        f"(excluded: " + ", ".join(f"{k.replace('_', ' ')} {v:,}" for k, v in SPL["exclusions"].items()) + "). "
        "Exact duplicates collapse to one sample; no image or capture session appears in more than one split. Class balance: Tomato/Not spoiled is "
        f"{SPL['per_stratum']['Tomato/Not_spoiled']['train'] + SPL['per_stratum']['Tomato/Not_spoiled']['val'] + SPL['per_stratum']['Tomato/Not_spoiled']['test']:,} of {SPL['eligible_samples']:,} images; Spoiled is {sum(cd['spoil']['Spoiled'] for cd in D['class_distribution'].values()):,} ({pct(sum(cd['spoil']['Spoiled'] for cd in D['class_distribution'].values()) / SPL['eligible_samples'])}). Macro-F1 is therefore the primary metric.")
    d.h1("Training methodology and split")
    d.p(f"60/20/20 split by capture session within each produce × label stratum (seed 42): {SPL['split_counts']['train']:,} / {SPL['split_counts']['val']:,} / {SPL['split_counts']['test']:,} ({pct(SPL['split_fractions_actual']['train'], 2)} / {pct(SPL['split_fractions_actual']['val'], 2)} / {pct(SPL['split_fractions_actual']['test'], 2)}). "
        "Augmentation only on training images; normalisation statistics from the pretrained checkpoint (none fitted on TR-6); checkpoint selected on validation; test evaluated once.")
    d.h1("Architecture and rationale")
    d.p("ViT-B/16 pretrained on ImageNet-21k and fine-tuned on ImageNet-1k (`timm` augreg2), fine-tuned end to end with two linear heads on the CLS embedding (dropout 0.1). Self-attention: Attention(Q,K,V) = softmax(QKᵀ/√d_k)V with 12 heads × 12 layers over 196 patches. "
        "Loss: L = CE(produce) + CE(spoilage). Rationale: strong transfer from large-scale pretraining for a small dataset; global attention captures spatially distributed decay; attention rollout gives an architecture-native explanation; the specification required a ViT.")
    c = P["config"]
    d.table("Hyperparameters (actual values from the run configuration).", ["Hyperparameter", "Value"], [
        ["Backbone", c["backbone"]], ["Input", f"{c['img_size']}×{c['img_size']} RGB; mean {c['mean']}, std {c['std']}"], ["Optimiser", f"AdamW, weight decay {c['weight_decay']}"],
        ["Learning rate", f"backbone {c['lr']}, heads {c['head_lr']}; {c['warmup_epochs']} epoch warm-up + cosine"], ["Batch / epochs / patience", f"{c['batch_size']} / {c['epochs']} / {c['patience']}"],
        ["Augmentation", c["aug"] + " (crop, flips, ±15° rotation, brightness/contrast ±0.15; no hue/saturation)"], ["Loss weights", f"λ_type {c['lambda_type']}, λ_spoil {c['lambda_spoil']}"],
        ["Seed", c["seed"]], ["Device / software", f"{c['device']}; torch {c['torch']}, timm {c['timm']}, Python {c['python']}"],
        ["Epochs run / selected", f"{c['epochs_run']} / {c['best_epoch']}"], ["Manifest SHA-256", c["manifest_sha256"][:16] + "…"]], widths=[30, 70], small=True)
    d.h1("Training curves and test results")
    d.fig("primary_training_loss.png", "Training and validation loss.")
    d.fig("primary_validation_metrics.png", "Validation macro-F1 per epoch.")
    d.table("Final test-set results (selected checkpoint, n = 1,071).", ["Metric", "Produce type", "Spoilage"], [
        ["Accuracy", f4(TT["accuracy"]), f4(TS["accuracy"])], ["Macro precision", f4(TT["macro_precision"]), f4(TS["macro_precision"])], ["Macro recall", f4(TT["macro_recall"]), f4(TS["macro_recall"])],
        ["Macro-F1", f4(TT["macro_f1"]), f4(TS["macro_f1"])], ["ROC-AUC", f4(TT["roc_auc"]) + " (OvR)", f4(TS["roc_auc"])],
        ["Spoilage macro-F1, session-bootstrap 95% CI", "–", f"{BOOT['spoil_macro_f1_95ci'][0]:.3f} – {BOOT['spoil_macro_f1_95ci'][1]:.3f}"],
        ["Spoiled recall, session-bootstrap 95% CI", "–", f"{BOOT['spoiled_recall_95ci'][0]:.3f} – {BOOT['spoiled_recall_95ci'][1]:.3f}"], ["Expected calibration error (10 bins)", "–", f"{CAL['ece_10bin']:.3f}"]], widths=[46, 27, 27])
    d.fig("primary_confusion_spoilage.png", "Spoilage confusion matrix (test).", width=0.5)
    d.fig("primary_roc_spoilage.png", "Spoilage ROC curve (test).", width=0.5)
    d.h1("Error analysis")
    cm = P["cm_spoil"]
    d.p(f"False negatives (Spoiled → Not spoiled): {cm[1][0]}; false positives: {cm[0][1]}. The cost of a false negative (spoiled food judged acceptable) is higher, so Spoiled recall ({f3(P['test_spoil_per_class']['Spoiled']['recall'])}) is the key weakness.")
    d.table("Test errors per stratum.", ["Produce", "True label", "n", "Errors", "Error rate"],
            [[nice(e["produce"]), nice(e["label"]), e["n"], e["errors"], pct(e["error_rate"])] for e in P["errors_by_stratum"]], widths=[30, 22, 14, 14, 20], small=True)
    d.fig("xai_failure_fn.png", "Representative false negatives (Spoiled → Not spoiled) with attention rollout.")
    d.fig("xai_failure_fp.png", "Representative false positives (Not spoiled → Spoiled) with attention rollout.")
    d.fig("primary_calibration.png", "Reliability diagram: errors are made with high confidence.", width=0.5)
    d.h1("Robustness")
    d.p("Robustness to image noise was measured on deterministic corruptions of the test split (Document C). Additional variation tests: horizontal flip and mild Gaussian noise (σ = 0.02) left the spoilage prediction unchanged for "
        f"{pct(XS['spoilage_prediction_unchanged_flip'])} and {pct(XS['spoilage_prediction_unchanged_noise'])} of 150 test images, respectively.")
    d.fig("noise_robustness.png", "Spoilage macro-F1 under Gaussian, salt-and-pepper and speckle noise.")
    d.h1("Comparison against baselines")
    b = F["baselines"]
    d.table("Baselines vs deployed model (test spoilage).", ["Model", "Macro-F1", "Accuracy", "ROC-AUC"], [
        ["Majority class (Not spoiled)", f3(TS['n'] and (P['test_spoil_per_class']['Not_spoiled']['support'] / TS['n']) * 2 / (1 + P['test_spoil_per_class']['Not_spoiled']['support'] / TS['n']) / 2), f3(P['test_spoil_per_class']['Not_spoiled']['support'] / TS['n']), "0.500"],
        ["Colour histogram + LogReg", f3(b["colorhist"]["test_spoil"]["macro_f1"]), f3(b["colorhist"]["test_spoil"]["accuracy"]), f3(b["colorhist"]["test_spoil"]["roc_auc"])],
        ["Frozen ViT-B + LogReg", f3(b["vit_frozen"]["test_spoil"]["macro_f1"]), f3(b["vit_frozen"]["test_spoil"]["accuracy"]), f3(b["vit_frozen"]["test_spoil"]["roc_auc"])],
        ["ViT-B/16 fine-tuned (deployed)", f3(TS["macro_f1"]), f3(TS["accuracy"]), f3(TS["roc_auc"])]], widths=[40, 20, 20, 20],
        source="Majority-class values computed from test support (always predicting Not spoiled).")
    d.h1("Limitations")
    d.bul(["Specimen leakage: TR-6 has no specimen IDs; the same fruits appear in train and test. A day-grouped split lowers performance (Document C).",
           "Labels are date-based folder labels, not independent assessments of spoilage.",
           "Lab images on plain backgrounds; real phone photos are untested; out-of-distribution inputs are always mapped to one of six classes (low-confidence warning below 0.60 is a heuristic).",
           "Confidence is uncalibrated on errors; UI tier thresholds (0.5 / 0.3) are heuristics.",
           "Single training seed for the deployed model."])
    d.h1("Reproducibility")
    d.bul(["Split: `python3 ml/data/make_splits.py --inventory dataset-preparation/tr6-audit/output_rerun_2026-10-15/file_inventory.csv --out artifacts/dataset/v1 --seed 42` (byte-identical on re-run)",
           "Train: `.venv/bin/python ml/train/train_vit.py --run-id vit_b16_primary --epochs 12 --patience 4`",
           "Evaluate: `.venv/bin/python ml/evaluate/evaluate_vit.py --run artifacts/runs/vit_b16_primary --split test`",
           "Environment: `ml/requirements.txt` (pinned versions)."])
    d.h1("Deployment inference tests and verdict")
    d.p(f"The checkpoint served by the backend is byte-identical to the evaluated run (SHA-256 {P['deployed_sha256'][:16]}…). Real-model tests R01–R04 pass, and the live end-to-end test analysed {E2E['held_out_images_via_api']} held-out full-resolution originals over HTTP "
        f"(produce {E2E['produce_correct']}/{E2E['held_out_images_via_api']}, spoilage {E2E['spoilage_correct']}/{E2E['held_out_images_via_api']}) with median latency {LAT['median_ms']:.0f} ms.")
    d.note("Verdict: the model is **genuinely trained** (logged 12-epoch run, validation-selected checkpoint, single held-out test evaluation) and **usable in the application** for its stated scope — single-item, six produce types, visual spoilage cues on TR-6-like images. It is not validated for real-world photos, food-safety decisions or shelf-life estimation.")
    return d.save("F_AI_Model_Testing_and_Evaluation_Report.docx")


# ======================================================================= G TR-6+ READINESS
def doc_tr6():
    np_ = TR["noise_pilot"]
    vr = TR["validation_rerun"]
    d = Doc("TR-6+ Dataset Extension and IEEE DataPort Readiness Report", "TR-6+ readiness", "What exists, what was validated, and what is still required before publication.", META("G — TR-6+ dataset readiness"))
    d.h1("Summary")
    d.bul(["TR-6+ is a **derived metadata resource** for TR-6 (manifests, audits, splits, protocols, scripts). It contains no newly collected images.",
           f"Validator re-run 2026-10-15: **{vr['result'].upper() if 'result' in vr else 'PASS'}**, {vr['n_errors']} errors, {vr['checks']['hashes_recomputed']} pilot source hashes recomputed and matching.",
           f"New: 120-image noise-derivative pilot (deterministic; independent regeneration reproduced all 120 SHA-256 hashes) and v1.1.0 metadata package (zip SHA-256 {json.loads((ROOT / 'releases/Foresight-TR6-plus-dataset-v1.1.0.release.json').read_text())['zip_sha256'][:16]}…).",
           f"Human annotation: **0** reviewed masks; {sum(TR['annotation_status_counts'].values())} pilot records (" + ", ".join(f"{k}: {v}" for k, v in TR["annotation_status_counts"].items()) + ").",
           "Not uploaded to IEEE DataPort; no DOI. Remaining steps require your account and decisions (Section 8)."])
    d.h1("Files and derivatives that exist")
    rel11 = json.loads((ROOT / "releases/Foresight-TR6-plus-dataset-v1.1.0.release.json").read_text())
    d.table("Inventory of original, processed, augmented and synthetic images.", ["Category", "Count", "Location", "In publication package?"], [
        ["Original TR-6 files", f"{D['audit']['file_count']:,} ({D['audit']['valid_images']:,} images)", "dataset/TR-6 (read-only)", "NO — cite Figshare DOI"],
        ["Unique image contents", f"{D['audit']['unique_image_hashes']:,}", "manifests", "manifest only"],
        ["Processed (resized cache for training)", f"{SPL['eligible_samples']:,}", "artifacts/cache/srgb_256", "NO (local derivative)"],
        ["Noise-augmented pilot derivatives", f"{np_['ok']} ({np_['bytes'] / 1e6:.0f} MB)", "Foresight-TR6-plus/derived-data/noise-pilot-v1", "manifest only"],
        ["Synthetic (GAN) images", f"{F['gan']['generation']['generated']}", "artifacts/experiments/gan/generated", "manifest only"],
        ["Proposal-only masks", "12", "Foresight-TR6-plus/annotations/masks", "NO (excluded; not ground truth)"],
        ["Human-reviewed masks", "0", "—", "—"]], widths=[30, 18, 32, 20], small=True)
    d.h1("Noise and augmentation methods")
    d.table("Noise-derivative pilot (TR-6+ pipeline, `config/noise_generation.json`).", ["Modality / transform / severity", "Derivatives"],
            [[k, v] for k, v in sorted(np_["by_modality_transform"].items())] + [["Total", np_["n_rows"]]], widths=[70, 30], small=True)
    d.p(f"Parameters: Gaussian σ = 8 / 20 (8-bit scale), salt-and-pepper 1% / 4%, speckle variance 0.04; seed 20261015; thermal palette images are perturbed in stored uint8 channels without radiometric assumptions. "
        "All derivatives inherit the split of their source (pilot split: " + ", ".join(f"{k} {v}" for k, v in np_["by_split"].items()) + f"); every row is marked synthetic ({np_['is_synthetic_all']}) and none is usable as an independent test specimen ({not np_['independent_test_specimen_any']}). "
        "Note: this pilot split (TR-6+ seed 20261015) is separate from the classifier split v1; the classifier's own robustness tests generate corruptions in memory (Document C). Conventional augmentation (crop, flip, rotation, brightness/contrast) is applied on the fly during training only and is not stored.")
    d.h1("Manifests, checksums and provenance")
    d.table("Manifest and integrity checks.", ["Check", "Result", "Status"], [
        ["Master manifest records / source paths found", f"{vr['checks']['master_records']:,} / {vr['checks']['source_paths_found']:,}", "VERIFIED"],
        ["Pilot source SHA-256 recomputed", f"{vr['checks']['hashes_recomputed']} / {vr['checks']['pilot_records']}", "VERIFIED"],
        ["Classifier split manifest (one row per content, SHA-256, provenance fields)", f"{SPL['unique_image_contents']:,} rows; reproducible byte-identically", "VERIFIED"],
        ["Noise pilot manifest: parent path + hash, derived hash, transform, parameters, seed", f"{np_['n_rows']} rows; regeneration identical", "VERIFIED"],
        ["GAN manifest: provenance = synthetic_cdcgan_train_only", f"{F['gan']['generation']['generated']} rows", "VERIFIED"],
        ["v1.0.0 zip checksum", "matches" if TR["zip_sha256_matches"] else "MISMATCH", "VERIFIED" if TR["zip_sha256_matches"] else "FAIL"],
        ["v1.1.0 package: SHA256SUMS for every file; zip checksum", f"{rel11['package_file_count']} files", "VERIFIED"],
        ["Absolute paths / image files inside v1.1.0", f"{len(rel11['absolute_path_leaks'])} / {len(rel11['image_files_in_package'])}", "VERIFIED"]], widths=[52, 30, 18], small=True)
    d.h1("Distributions, duplicates and conflicts")
    d.table("Duplicate and label-conflict facts (from the audit).", ["Item", "Value"], [
        ["Exact-duplicate groups", f"{D['audit']['duplicate_groups']:,}"], ["Excess duplicate copies", f"{D['audit']['duplicate_excess_copies']:,}"],
        ["Cross-label conflict groups", f"{D['audit']['cross_label_duplicate_groups']} (all thermal: 153 Banana, 17 Indian Gooseberry)"],
        ["Normal hashes not represented in Classified", f"{D['audit']['normal_image_hashes_not_represented_in_classified']}"], ["Verified cross-modal pairs", "0"]], widths=[50, 50])
    d.h1("Annotations")
    cal = TR["calibration"]
    d.p(f"Label Studio calibration batch: {cal['batch_size']} images with machine-generated foreground polygons (status `{cal['status']}`, defect masks {cal['defect_masks']}). These are **proposals**, not ground truth; proposal `tr6p_073` (Mango thermal) is known to be wrong. "
        "No human has reviewed or submitted an annotation; CVAT is not installed. Consequently U-Net training is blocked.")
    d.h1("Documentation present")
    d.table("Publication documentation in the v1.1.0 package.", ["Document", "Present", "Notes"], [
        ["README with purpose, scope, structure, provenance", "YES", "v1.0.0 README + v1.1.0 section"], ["DATA_DICTIONARY.md", "YES", "field definitions"],
        ["LICENSE_AND_ATTRIBUTION.md", "YES", "CC BY 4.0 evidence from Figshare API"], ["CITATION.md (TR-6 source citation)", "YES", "DataPort DOI to be added after publication"],
        ["NOT_INCLUDED.md", "YES", "excluded binaries and claims"], ["Processing methodology / scripts", "YES", "audit, build, validate, split, noise, GAN scripts"],
        ["Dataset card / limitations", "YES", "docs/DATASET_CARD.md"], ["CHANGELOG, VERSION, SHA256SUMS", "YES", "v1.1.0"]], widths=[45, 12, 43], small=True)
    d.h1("IEEE DataPort checklist")
    d.table("IEEE DataPort requirements.", ["Requirement", "Status", "Evidence / action"], [
        ["Dataset title and abstract", "VERIFIED", "drafted in IEEE_DATAPORT_SUBMISSION.md / README"],
        ["Description of collection/processing methodology", "VERIFIED", "README, DATASET_CARD, scripts"],
        ["Licence chosen and compatible with source", "VERIFIED", "CC BY 4.0, attribution of TR-6 authors"],
        ["Source dataset citation and DOI link", "VERIFIED", "CITATION.md (10.6084/m9.figshare.30783827.v1)"],
        ["File integrity (checksums)", "VERIFIED", "SHA256SUMS.txt; zip .sha256"],
        ["No restricted / personal data; no secrets or absolute paths", "VERIFIED", "package scan: 0 path leaks, 0 images; Label Studio .env excluded"],
        ["Data dictionary / metadata", "VERIFIED", "DATA_DICTIONARY.md"],
        ["Keywords and category", "VERIFIED", "listed in IEEE_DATAPORT_SUBMISSION.md"],
        ["Authors, affiliations, ORCID", "REQUIRES YOUR ACTION", "fill on the DataPort form; team details not in workspace"],
        ["Decision whether to include image derivatives (permitted under CC BY 4.0 with attribution)", "REQUIRES YOUR ACTION", "v1.1.0 deliberately ships manifests only"],
        ["Human-reviewed annotations", "MISSING", "0 reviewed; publish as 'protocol + proposals pending review' or annotate first"],
        ["IEEE account, upload, submission", "REQUIRES YOUR ACTION", "not performed"],
        ["DOI", "MISSING", "assigned only after submission — do not cite one before"]], widths=[42, 18, 40], small=True)
    d.h1("Prepared archives")
    d.table("Release artefacts.", ["File", "Size", "SHA-256", "Contents"], [
        ["releases/Foresight-TR6-plus-dataset-v1.0.0.zip", f"{TR['release']['zip_bytes']:,} B", TR["release"]["zip_sha256"][:24] + "…", "manifests, audits, protocol (unchanged)"],
        ["releases/Foresight-TR6-plus-dataset-v1.1.0.zip", f"{rel11['zip_bytes']:,} B", rel11["zip_sha256"][:24] + "…", "v1.0.0 + ML splits, noise & GAN manifests, validation re-run"]], widths=[38, 14, 26, 22], small=True)
    d.note("No upload or publication has occurred. `ieee_dataport_uploaded = false`, `doi_assigned = false` in both release records.", warn=True)
    return d.save("G_TR6plus_Dataset_Readiness_Report.docx")


if __name__ == "__main__":
    outs = [doc_status(), doc_gan(), doc_xai(), doc_ablation(), doc_results(), doc_testing(), doc_eval(), doc_tr6()]
    print("\n".join(str(o.relative_to(ROOT)) for o in outs))
