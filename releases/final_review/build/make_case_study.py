"""make_case_study.py — Review 3 case-study document (DOCX), numbers from saved results."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_reports as B  # noqa: E402  (Doc renderer, facts and helpers; documents are not rebuilt on import)

F, P, TS, SPL, S2 = B.F, B.P, B.TS, B.SPL, B.S2
VD, UP, SL = B.VDR, B.UP, B.SL
f3, pct, nice = B.f3, B.pct, B.nice
OUT = B.ROOT / "releases/review3/Foresight_Case_Study.docx"

d = B.Doc("Case Study: Foresight — Visual Produce-Spoilage Estimation with Leakage-Controlled Deep Learning", "Case study",
          "How a public fruit-spoilage dataset was audited, modelled, explained and turned into a working, tested web application.",
          [("Project", "Foresight"), ("Document", "Review 3 — case study"), ("Date", B.DATE),
           ("Team", "[Team names and roll numbers]"), ("Repository", "/Users/nandu/Downloads/foresight")])

d.h1("Executive summary")
d.p(f"Foresight estimates, from one photograph of a single fruit or vegetable, its produce type, whether it shows the visual characteristics of spoilage, whether decay is visible, the decayed area, a proxy shelf-life and an explanation heat-map. "
    f"The core model, a fine-tuned ViT-B/16, reaches a held-out test spoilage macro-F1 of **{f3(TS['macro_f1'])}** (accuracy {pct(TS['accuracy'])}, ROC-AUC {f3(TS['roc_auc'])}) and perfect produce classification on {TS['n']:,} test images. "
    "It is integrated into a FastAPI backend and a React interface, and verified end to end with automated, contract and browser tests.")
d.p("The most important lesson of the case is that **the dataset determined the validity of the results more than the model did**: the public dataset contained complete duplicate copies, conflicting labels and date-based labels, all of which had to be found and controlled before any metric could be trusted.")
d.kv([("Headline result", f"spoilage macro-F1 {f3(TS['macro_f1'])} (session-bootstrap 95% CI {f3(P['bootstrap']['spoil_macro_f1_95ci'][0])}–{f3(P['bootstrap']['spoil_macro_f1_95ci'][1])})"),
      ("Key risk found", f"a random split would leak an exact copy of ~60% of test images into training"),
      ("Key insight from human annotation", f"only {VD['dataset_label_vs_human']['spoiled_labelled_with_visible_decay']} 'Spoiled'-labelled images show visible decay"),
      ("Status", "working prototype; validated U-Net and true shelf-life remain future work")])

d.h1("Background and problem")
d.p("Post-harvest loss of fruit and vegetables is a major source of food waste in India. Retailers, exporters and households decide what to sell, use or discard by visual inspection, which is subjective and slow. "
    "Most published fruit-quality models answer only 'spoiled or not' and are rarely checked for data leakage, so reported accuracies can be inflated.")
d.p("The project goal was a research prototype that: (1) uses only a phone-style RGB photo; (2) produces several interpretable outputs rather than a single label; (3) explains its decisions; and (4) reports only metrics that survive leakage-controlled evaluation. "
    "It is explicitly not a food-safety tool: the interface states 'visual estimate — not a food-safety guarantee'.")

d.h1("Stakeholders and requirements")
d.table("Stakeholders and what they need from the system.", ["Stakeholder", "Need", "How Foresight addresses it"], [
    ["Household / retailer", "Quick, understandable advice", "Card with produce type, spoilage, decay %, shelf-life estimate and a plain-language action"],
    ["Course reviewers", "Real models, real metrics, explainability", "Logged training runs, untouched test set, ablations, XAI, test evidence"],
    ["Researchers / dataset users", "Reusable, leakage-safe data", "TR-6+ manifests, split files and validation scripts (IEEE DataPort package)"],
    ["Developers", "Maintainable, testable system", "FastAPI + React with 37 backend/ML tests, 7 frontend tests and an E2E script"]], widths=[22, 30, 48])

d.h1("The data challenge")
a = F["dataset"]["audit"]
d.p(f"The project uses TriModal Ripeness 6 (TR-6): {a['file_count']:,} files (19.8 GiB) of sRGB images, thermal IR-fusion images and methane logs for six produce types. A full audit before modelling found:")
d.bul([f"Every one of the {a['classified_images_exactly_duplicated_in_normal']:,} images in the 'Classified' folder is a byte-identical copy of an image in the 'Normal' folder — only {a['unique_image_hashes']:,} unique images exist.",
       f"{a['cross_label_duplicate_groups']} images appear under both 'Spoiled' and 'Not_spoiled' (all thermal) — contradictory labels.",
       "Each capture session holds 17 near-identical views of one fruit, and each produce type is a small number of specimens photographed over consecutive days.",
       "Within every produce type, all 'Not spoiled' captures precede all 'Spoiled' captures: the label marks a stage of a time series."])
lk = F["split_leakage"]
d.table("Measured leakage of test images into training for different split strategies (no model needed).", ["Split strategy", "Exact duplicate in train", "Same capture session in train", "Same produce-day in train"],
        [[r["split_scheme"], f"{r['test_with_exact_duplicate_in_train_pct']:.1f}%", f"{r['test_with_same_session_in_train_pct']:.1f}%", f"{r['test_with_same_produce_day_in_train_pct']:.1f}%"] for r in lk],
        widths=[40, 20, 20, 20], small=True)
d.p(f"Decision: de-duplicate by SHA-256, exclude conflicting labels, use sRGB only (the app receives phone photos), and split 60/20/20 by capture session within each produce × label stratum. This produced {SPL['eligible_samples']:,} eligible images: {SPL['split_counts']['train']:,} train, {SPL['split_counts']['val']:,} validation and {SPL['split_counts']['test']:,} test, with zero duplicate or session leakage.")
d.fig("split_distribution.png", "Session-grouped 60/20/20 split per produce × label stratum.")

d.h1("Solution approach")
d.h2("Core model")
d.p(f"A pretrained ViT-B/16 was fine-tuned with two heads (produce type, spoilage) using AdamW (backbone LR {P['config']['lr']}, heads {P['config']['head_lr']}), conservative augmentation that avoids colour shifts, and early stopping on validation macro-F1. "
    f"Training took {P['train_minutes']} minutes on an Apple M5 laptop; the checkpoint from epoch {P['best_epoch']} was selected on validation and scored once on test.")
d.h2("Supporting models and experiments")
d.table("Components and their role.", ["Component", "Role", "In the app?"], [
    ["ViT-B/16 two-head classifier", "produce type + spoilage", "YES"], ["Visible-decay probe", "image-level visible decay, trained on human labels", "YES"],
    ["Pilot U-Net (ResNet-18 encoder)", "fruit and decay mask, decay coverage %", "YES (labelled pilot)"], ["Ridge regressor", "proxy shelf-life (days until 'Spoiled' label)", "YES (labelled proxy)"],
    ["Attention rollout", "explanation heat-map", "YES"], ["Conditional DCGAN", "synthetic training images (experiment)", "research only"],
    ["DnCNN / median filter", "denoising (robustness experiment)", "research only"], ["Logistic-regression baselines, K-means", "baselines and exploratory clustering", "research only"]], widths=[34, 46, 20])
d.h2("System architecture")
d.p("React (Vite) UI → FastAPI backend (upload validation, structured errors, CORS) → inference service (models loaded once at startup) → deterministic result composer (warnings, overlays) → SQLite history. Uploaded images are never stored. Mock predictions exist only for UI development, are off by default and are labelled 'DEMO MOCK DATA'.")

d.h1("Results")
d.table("Held-out test results of the deployed model (n = 1,071).", ["Task", "Accuracy", "Macro precision", "Macro recall", "Macro-F1", "ROC-AUC"], [
    ["Produce type", f3(B.TT["accuracy"]), f3(B.TT["macro_precision"]), f3(B.TT["macro_recall"]), f3(B.TT["macro_f1"]), f3(B.TT["roc_auc"])],
    ["Spoilage", f3(TS["accuracy"]), f3(TS["macro_precision"]), f3(TS["macro_recall"]), f3(TS["macro_f1"]), f3(TS["roc_auc"])]], small=True)
d.fig("primary_confusion_spoilage.png", "Spoilage confusion matrix on the test set.", width=0.45)
b = F["baselines"]
d.table("Model comparison on the same test split (spoilage macro-F1).", ["Model", "Spoilage macro-F1"], [
    ["Colour histogram + logistic regression", f3(b["colorhist"]["test_spoil"]["macro_f1"])], ["Frozen ViT-B/16 + logistic regression", f3(b["vit_frozen"]["test_spoil"]["macro_f1"])],
    ["ViT-S/16, real images only (3 seeds)", B.pm(S2["noaug"]["test_spoil_macro_f1"])], ["ViT-S/16 + conventional augmentation (3 seeds)", B.pm(S2["aug"]["test_spoil_macro_f1"])],
    ["ViT-S/16 + augmentation + GAN images (3 seeds)", B.pm(S2["gan"]["test_spoil_macro_f1"])], ["ViT-B/16 fine-tuned (deployed)", f3(TS["macro_f1"])]], widths=[70, 30])
d.bul([f"Conventional augmentation helped slightly ({B.diff_text('aug_minus_noaug')}); GAN images did not ({B.diff_text('gan_minus_aug')}).",
       f"Testing on unseen capture days lowered macro-F1 by {abs(F['ablation_pairs']['day_minus_session_aug']['mean']):.3f} (3 seeds) — the main score is optimistic about new days.",
       "Strong synthetic noise lowers spoilage macro-F1 to about 0.78–0.80; a 3×3 median filter repairs salt-and-pepper noise.",
       f"Attention rollout focuses on the fruit; masking the highlighted patches lowers confidence {F['xai']['faithfulness']['mean_drop_top_rollout'] / F['xai']['faithfulness']['mean_drop_random']:.0f}× more than masking random patches."])
d.fig("xai_failure_fn.png", "Attention rollout on test errors: 'Spoiled'-labelled fruit that looks fresh.")

d.h1("Human annotation study")
d.p(f"To test what the 'Spoiled' label means, 180 images (stratified across produce, label and split) were reviewed by a human annotator in Label Studio. Of {VD['n_definite']} definite decisions, the human saw visible decay in **{VD['dataset_label_vs_human']['spoiled_labelled_with_visible_decay']}** 'Spoiled'-labelled images and in {VD['dataset_label_vs_human']['not_spoiled_labelled_with_visible_decay']} 'Not spoiled' ones — overall agreement {pct(VD['dataset_label_vs_human']['agreement'])}.")
d.fig("human_vs_dataset_label.png", "Share of images judged to show visible decay, per produce and dataset label.")
d.p(f"These decisions trained a visible-decay check that reached {f3(VD['probe_test']['accuracy'])} accuracy on {VD['probe_test']['n']} held-out test images (95% CI {VD['probe_test']['accuracy_95ci_wilson'][0]:.2f}–{VD['probe_test']['accuracy_95ci_wilson'][1]:.2f}). "
    "The annotation round recorded image-level decisions but no drawn polygons, so the U-Net in the app is a pilot trained on machine-generated masks gated by those human decisions.")

d.h1("Implementation and verification")
E = F["tests"]["e2e"]
d.table("Verification evidence.", ["Check", "Result"], [
    ["Backend + ML automated tests (pytest)", F["tests"]["pytest_summary"]], ["Frontend tests (Vitest)", "7 passed"], ["Frontend production build", "passes"],
    ["Live end-to-end checks", f"{E['passed']}/{E['total']}; {E['produce_correct']}/{E['held_out_images_via_api']} produce and {E['spoilage_correct']}/{E['held_out_images_via_api']} spoilage correct on held-out originals"],
    ["UI ↔ API contract", f"{F['tests']['ui_contract']['fields_present']}/{F['tests']['ui_contract']['fields_checked']} fields present"],
    ["Median end-to-end latency", f"{F['tests']['latency']['median_ms']:.0f} ms (Apple M5, MPS)"],
    ["Failure handling", "415 wrong type, 400 corrupt, 413 too large, 503 model missing — all shown in the UI"]], widths=[40, 60])

d.h1("Challenges and lessons learned")
d.table("What went wrong and what was learned.", ["Challenge", "What happened", "Lesson"], [
    ["Duplicated dataset", "Classified folder was a copy of Normal", "Hash every file before splitting; never trust folder structure"],
    ["Hidden leakage", "17 views per session, same fruit over days", "Group splits by capture session; measure day-level leakage too"],
    ["Label meaning", "'Spoiled' follows date, not always visible decay", "Validate labels with humans before claiming what a model detects"],
    ["Unstable ablation", "First ViT-S run peaked at epoch 1 (LR too high)", "Use several seeds and report validation and test separately"],
    ["GAN quality", "Synthetic images mostly unrecognisable to the classifier", "Check synthetic data with a real-data model before training on it"],
    ["Annotation", "First round produced decisions but no polygons", "Pilot the annotation tool and give a short hands-on guide first"],
    ["Honest UI", "Original UI showed fabricated detections and shelf-life", "Show only what a model produced; label pilots and proxies"]], widths=[18, 38, 44], small=True)

d.h1("Ethical considerations and SDG relevance")
d.bul(["The tool never claims food is safe to eat; uncertainty, pilot and proxy outputs are labelled in the interface.",
       "No personal data is collected; uploaded images are not stored.",
       "The dataset is CC BY 4.0 and its authors are credited; derived data is shared as metadata only.",
       "**SDG 12.3** (halve food waste and reduce food losses along supply chains): early visual triage can prioritise produce for use before it is lost.",
       "**SDG 2** (zero hunger): reducing post-harvest loss increases available food."])

d.h1("Limitations")
d.bul(["The same physical fruits appear in training and test (TR-6 has no specimen IDs).", "All images are lab photos on plain backgrounds; real phone photos are untested.",
       "Confidence is poorly calibrated on errors.", "The U-Net is a pilot trained on machine-generated masks; shelf-life is a proxy derived from dataset labels.",
       "Single-item photos only; no multi-item detection."])

d.h1("Conclusion and next steps")
d.p("Foresight shows that a leakage-controlled, explainable and fully tested spoilage prototype can be built from a public dataset on a laptop. Its value lies as much in the auditing and evaluation discipline as in the model accuracy.")
d.num(["Draw human decay polygons and train a validated U-Net.", "Collect and evaluate on real-world phone photos.", "Calibrate confidence scores.",
       "Deploy the backend and frontend to a public host.", "Publish TR-6+ on IEEE DataPort."])

d.h1("References")
d.num(["T. Bagyammal, Y. A. P. T. S, K. Deepak and D. Unnikrishnan, “TriModal Ripeness 6,” figshare, 2025, doi: 10.6084/m9.figshare.30783827.v1.",
       "A. Dosovitskiy et al., “An image is worth 16x16 words: Transformers for image recognition at scale,” in Proc. ICLR, 2021.",
       "S. Abnar and W. Zuidema, “Quantifying attention flow in transformers,” in Proc. ACL, 2020.",
       "O. Ronneberger, P. Fischer and T. Brox, “U-Net: Convolutional networks for biomedical image segmentation,” in Proc. MICCAI, 2015.",
       "A. Radford, L. Metz and S. Chintala, “Unsupervised representation learning with deep convolutional generative adversarial networks,” in Proc. ICLR, 2016.",
       "K. Zhang, W. Zuo, Y. Chen, D. Meng and L. Zhang, “Beyond a Gaussian denoiser: Residual learning of deep CNN for image denoising,” IEEE Trans. Image Process., vol. 26, no. 7, 2017."])

import shutil  # noqa: E402
OUT.parent.mkdir(parents=True, exist_ok=True)
shutil.move(str(d.save("_review3_case_study.docx")), OUT)
print(OUT)
