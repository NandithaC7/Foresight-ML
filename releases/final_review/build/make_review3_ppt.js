// make_review3_ppt.js — Review 3 presentation for Foresight (all numbers read from saved results)
// Usage: node make_review3_ppt.js <out.pptx>
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const ROOT = path.resolve(__dirname, "../../..");
const FIG = path.join(ROOT, "releases/final_review/figures");
const F = JSON.parse(fs.readFileSync(path.join(__dirname, "facts.json"), "utf8"));
const J = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));
const VD = J("artifacts/experiments/visible_decay/results.json");
const UP = J("artifacts/experiments/unet_pilot/results.json");
const SL = J("artifacts/experiments/shelf_life_proxy/results.json");
const out = process.argv[2];

const THEME = {
  name: "Foresight Produce", headFontFace: "Cambria", bodyFontFace: "Calibri",
  colors: { dk1: "1E2A24", lt1: "FFFFFF", dk2: "2F4A3D", lt2: "EEF3EF", accent1: "2F6B4F", accent2: "C1622E",
            accent3: "8FA99C", accent4: "B59A3C", accent5: "7A8FB0", accent6: "5A6B60", hlink: "2F6B4F", folHlink: "6D5A8F" },
};
const HEX = THEME.colors;
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Foresight — Review 3";
const C = pres.SchemeColor;
const W = 13.333, H = 7.5;

pres.defineSlideMaster({
  title: "TITLE_DARK", background: { color: HEX.dk2 },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.2, w: 11.7, h: 1.6, fontSize: 44, bold: true, color: C.background1, fontFace: THEME.headFontFace, valign: "bottom" }, text: "" } },
            { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.95, w: 11.7, h: 1.4, fontSize: 18, color: "D7E4DA", valign: "top" }, text: "" } }],
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: HEX.lt1 },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.85, fontSize: 32, bold: true, color: C.text2, fontFace: THEME.headFontFace, valign: "middle" }, text: "" } }],
  slideNumber: { x: 12.4, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: "7A867E" },
});

function imgSize(p) {
  const b = fs.readFileSync(p);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function fitImage(slide, name, x, y, maxW, maxH, alt) {
  const p = path.join(FIG, name); const s = imgSize(p);
  let w = maxW, h = (s.h / s.w) * w;
  if (h > maxH) { h = maxH; w = (s.w / s.h) * h; }
  slide.addImage({ path: p, x: x + (maxW - w) / 2, y: y + (maxH - h) / 2, w, h, altText: alt || name, objectName: "img_" + name });
}
function bullets(slide, items, x, y, w, h, size = 16) {
  slide.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 8 } })),
    { x, y, w, h, fontSize: size, color: C.text1, valign: "top", isTextBox: true, objectName: "bullets" });
}
function stat(slide, x, y, w, value, label, color) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 1.55, rectRadius: 0.12, fill: { color: C.background2 }, line: { color: C.background2 }, objectName: "stat_card" });
  slide.addText(value, { x: x + 0.15, y: y + 0.12, w: w - 0.3, h: 0.85, fontSize: 36, bold: true, color: color || C.accent1, fontFace: THEME.headFontFace, isTextBox: true, margin: 0 });
  slide.addText(label, { x: x + 0.15, y: y + 0.95, w: w - 0.3, h: 0.5, fontSize: 12, color: C.text1, isTextBox: true, margin: 0, valign: "top" });
}
function caption(slide, t, x, y, w) {
  slide.addText(t, { x, y, w, h: 0.35, fontSize: 11, italic: true, color: "5A6B60", isTextBox: true, margin: 0 });
}
const f3 = (x) => x.toFixed(3);
const pct = (x, d = 1) => (100 * x).toFixed(d) + "%";
const P = F.primary, TS = P.test_spoil, SPL = F.dataset.split, S2 = F.ablation_v2_summary;

// 1 Title
pres.addSection({ title: "Introduction" });
let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Introduction" });
s.addText("Foresight: Visual Produce-Spoilage Estimation", { placeholder: "title" });
s.addText("Review 3 — trained models, integrated web application, evaluation and deployment readiness", { placeholder: "body" });
s.addNotes("Introduce the team and the goal of Review 3: show real models running inside the application, compare models, show XAI, and report test results.");

// 2 Problem
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
s.addText("From one photo to an actionable freshness estimate", { placeholder: "title" });
bullets(s, ["Post-harvest loss is high for perishable fruit and vegetables in Indian supply chains",
  "Foresight takes one phone-style photo of a single item and returns: produce type, spoilage estimate, visible-decay check, decay mask, proxy shelf-life and an explanation heat-map",
  "Six produce types: banana, carrot, guava, Indian gooseberry, mango, tomato",
  "Research prototype — a visual estimate, not a food-safety guarantee"], 0.6, 1.5, 6.2, 5.0);
fitImage(s, "xai_class_gallery_part1.png", 7.1, 1.5, 5.7, 4.8, "Example inputs and attention maps");
caption(s, "Real test images with the model's attention rollout", 7.1, 6.4, 5.7);

// 3 Dataset
pres.addSection({ title: "Data" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Data" });
s.addText("TR-6 audited: duplicates and conflicts removed", { placeholder: "title" });
stat(s, 0.6, 1.5, 2.9, F.dataset.audit.file_count.toLocaleString("en-US"), "files audited (19.8 GiB)");
stat(s, 3.7, 1.5, 2.9, F.dataset.audit.unique_image_hashes.toLocaleString("en-US"), "unique images (Classified = copy of Normal)");
stat(s, 6.8, 1.5, 2.9, String(F.dataset.audit.cross_label_duplicate_groups), "contents with conflicting labels — excluded", C.accent2);
stat(s, 9.9, 1.5, 2.9, SPL.eligible_samples.toLocaleString("en-US"), "eligible sRGB images used");
fitImage(s, "split_distribution.png", 0.6, 3.3, 7.4, 3.6, "Split distribution");
bullets(s, [`60/20/20 split by capture session: ${SPL.split_counts.train} / ${SPL.split_counts.val} / ${SPL.split_counts.test}`,
  "0 duplicate images and 0 sessions shared across splits", "A random split would put an exact copy of ~60% of test images into training"], 8.3, 3.4, 4.5, 3.4, 15);

// 4 Architecture
pres.addSection({ title: "System" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "System" });
s.addText("Architecture: React UI, FastAPI, models, SQLite", { placeholder: "title" });
const boxes = [["React + Vite UI", "upload, results, history, dashboard"], ["FastAPI", "validation, errors, CORS"], ["Inference", "ViT-B/16 + add-on models"], ["Result composer", "warnings, overlays"], ["SQLite history", "no images stored"]];
boxes.forEach(([t, d], i) => {
  const x = 0.6 + i * 2.5;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.7, w: 2.15, h: 1.5, rectRadius: 0.12, fill: { color: i === 2 ? C.accent1 : C.background2 }, line: { color: i === 2 ? C.accent1 : C.background2 }, objectName: "arch_box" });
  s.addText([{ text: t, options: { bold: true, breakLine: true, fontSize: 15 } }, { text: d, options: { fontSize: 12 } }],
    { x: x + 0.1, y: 1.8, w: 1.95, h: 1.3, color: i === 2 ? C.background1 : C.text1, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  if (i < boxes.length - 1) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.17, y: 2.3, w: 0.3, h: 0.3, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "arrow" });
});
const models = [["ViT-B/16 classifier", "produce type + spoilage"], ["Visible-decay check", "probe trained on human labels"], ["Pilot U-Net", "fruit + decay mask, coverage %"], ["Proxy shelf-life", "days until 'Spoiled' label"], ["Attention rollout", "XAI heat-map"]];
models.forEach(([t, d], i) => {
  const x = 0.6 + i * 2.5;
  s.addShape(pres.shapes.OVAL, { x: x + 0.82, y: 3.75, w: 0.5, h: 0.5, fill: { color: C.accent2 }, line: { color: C.accent2 }, objectName: "dot" });
  s.addText(String(i + 1), { x: x + 0.82, y: 3.75, w: 0.5, h: 0.5, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  s.addText([{ text: t, options: { bold: true, breakLine: true } }, { text: d }], { x, y: 4.35, w: 2.15, h: 1.0, fontSize: 13, color: C.text1, align: "center", valign: "top", isTextBox: true, margin: 0 });
});
s.addText("Every response carries the model version, warnings and a disclaimer; mock mode is off by default and labelled DEMO MOCK DATA if ever enabled.",
  { x: 0.6, y: 5.8, w: 12.1, h: 0.7, fontSize: 15, color: C.text2, isTextBox: true });

// 5 ViT model
pres.addSection({ title: "Models and results" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Models and results" });
s.addText("Primary model: pretrained ViT-B/16 with two heads", { placeholder: "title" });
const cfg = P.config;
const rows = [["Backbone", "ViT-B/16 (ImageNet-21k → 1k), fine-tuned"], ["Heads", "produce type (6) + spoilage (2)"], ["Loss", "CE(type) + CE(spoilage)"], ["Optimiser / LR", `AdamW, ${cfg.lr} backbone, ${cfg.head_lr} heads`],
  ["Batch / epochs", `${cfg.batch_size} / ${cfg.epochs_run}, best epoch ${cfg.best_epoch} (validation)`], ["Augmentation", "crop, flips, ±15° rotation, brightness/contrast"], ["Training time", `${P.train_minutes} min on Apple M5 (MPS)`]];
s.addTable(rows.map((r, i) => r.map((c, j) => ({ text: c, options: { bold: j === 0, fill: { color: i % 2 ? "FFFFFF" : HEX.lt2 }, color: HEX.dk1 } }))),
  { x: 0.6, y: 1.5, w: 6.2, colW: [1.9, 4.3], fontSize: 14, fontFace: "Calibri", border: { type: "solid", pt: 0.5, color: "C9D6CD" }, rowH: 0.55 });
fitImage(s, "primary_validation_metrics.png", 7.1, 1.5, 5.7, 4.6, "Validation curves");
caption(s, "Validation macro-F1 per epoch; checkpoint selected on validation only", 7.1, 6.2, 5.7);

// 6 Test results
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Models and results" });
s.addText("Held-out test results (1,071 images, scored once)", { placeholder: "title" });
stat(s, 0.6, 1.5, 2.6, f3(TS.macro_f1), "spoilage macro-F1");
stat(s, 3.4, 1.5, 2.6, pct(TS.accuracy), "spoilage accuracy");
stat(s, 0.6, 3.25, 2.6, f3(TS.roc_auc), "spoilage ROC-AUC");
stat(s, 3.4, 3.25, 2.6, pct(P.test_type.accuracy, 0), "produce-type accuracy");
s.addText(`Session-bootstrap 95% CI for macro-F1: ${f3(P.bootstrap.spoil_macro_f1_95ci[0])}–${f3(P.bootstrap.spoil_macro_f1_95ci[1])}. Weak spot: Spoiled recall ${f3(P.test_spoil_per_class.Spoiled.recall)} (mostly gooseberry and tomato).`,
  { x: 0.6, y: 5.0, w: 5.4, h: 1.3, fontSize: 14, color: C.text1, isTextBox: true });
fitImage(s, "primary_confusion_spoilage.png", 6.4, 1.4, 3.2, 3.4, "Spoilage confusion matrix");
fitImage(s, "primary_roc_spoilage.png", 9.7, 1.4, 3.1, 3.4, "ROC curve");
fitImage(s, "primary_errors_by_stratum.png", 6.4, 4.9, 6.4, 2.0, "Errors by stratum");

// 7 Model comparison (native chart)
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Models and results" });
s.addText("Model comparison: fine-tuned ViT-B/16 is best", { placeholder: "title" });
const b = F.baselines;
const labels = ["Colour hist. + LogReg", "Frozen ViT-B + LogReg", "ViT-S real only", "ViT-S + conv. aug", "ViT-S + aug + GAN", "ViT-B/16 (deployed)"];
const vals = [b.colorhist.test_spoil.macro_f1, b.vit_frozen.test_spoil.macro_f1, S2.noaug.test_spoil_macro_f1.mean, S2.aug.test_spoil_macro_f1.mean, S2.gan.test_spoil_macro_f1.mean, TS.macro_f1].map((v) => +v.toFixed(3));
s.addChart(pres.charts.BAR, [{ name: "Test spoilage macro-F1", labels, values: vals }], {
  x: 0.6, y: 1.4, w: 8.0, h: 5.4, barDir: "bar", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.000", valAxisLabelFormatCode: "0.00", dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt",
  valAxisMinVal: 0.7, valAxisMaxVal: 1.0, catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", valAxisLabelFontSize: 10,
  chartColors: [HEX.accent1], valGridLine: { color: "E3E9E5", size: 0.5 }, catGridLine: { style: "none" }, showLegend: false,
  showTitle: true, title: "Test spoilage macro-F1 (ViT-S = mean of 3 seeds)", titleFontSize: 13, titleFontFace: "+mn-lt", catAxisLabelColor: HEX.dk1, valAxisLabelColor: "5A6B60",
});
bullets(s, [`Fine-tuning beats frozen features by ${(TS.macro_f1 - b.vit_frozen.test_spoil.macro_f1).toFixed(3)}`, `Conventional augmentation: ${F.ablation_pairs.aug_minus_noaug.mean >= 0 ? "+" : ""}${F.ablation_pairs.aug_minus_noaug.mean.toFixed(3)}, positive on all 3 seeds`,
  `GAN images: ${F.ablation_pairs.gan_minus_aug.mean.toFixed(3)}, not consistent across seeds — no benefit`, "Same split, same untouched test set for every model"], 8.9, 1.6, 3.9, 5.0, 15);

// 8 GAN
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Models and results" });
s.addText("GAN augmentation: tested, no measurable gain", { placeholder: "title" });
fitImage(s, "gan_label_consistency.png", 0.6, 1.4, 7.2, 3.2, "GAN label consistency");
fitImage(s, "gan_nearest_neighbour.png", 0.6, 4.75, 7.2, 2.1, "GAN nearest neighbours");
bullets(s, ["Conditional DCGAN, 64×64, 12 classes, trained on the training split only", `480 synthetic images; real-data ViT recognises the intended produce in only ${pct(F.gan.quality.label_consistency_by_primary_vit.overall_type_match)}`,
  "No memorisation: generated images are farther from training images than real images are from each other",
  `3-seed ViT-S result: ${S2.gan.test_spoil_macro_f1.mean.toFixed(3)} with GAN vs ${S2.aug.test_spoil_macro_f1.mean.toFixed(3)} without`], 8.1, 1.5, 4.7, 5.2, 15);

// 9 Ablation: splits + noise
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Models and results" });
s.addText("Ablations: split design and noise matter most", { placeholder: "title" });
fitImage(s, "noise_robustness.png", 0.6, 1.4, 7.6, 2.8, "Noise robustness");
const lk = F.split_leakage;
s.addTable([[{ text: "Split scheme", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }, { text: "Test images with same-day image in train", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }],
  ["Random (raw files)", lk[0].test_with_same_produce_day_in_train_pct.toFixed(1) + "% (+ " + lk[0].test_with_exact_duplicate_in_train_pct.toFixed(0) + "% exact duplicates)"],
  ["Session-grouped (used)", lk[2].test_with_same_produce_day_in_train_pct.toFixed(1) + "%"], ["Day-grouped (sensitivity)", lk[3].test_with_same_produce_day_in_train_pct.toFixed(1) + "%"]],
  { x: 0.6, y: 4.5, w: 7.6, colW: [3.0, 4.6], fontSize: 13, fontFace: "Calibri", color: HEX.dk1, border: { type: "solid", pt: 0.5, color: "C9D6CD" }, rowH: 0.45 });
bullets(s, [`Unseen-days test: ${F.daysplit_v2_summary.test_spoil_macro_f1.mean.toFixed(3)} vs ${S2.aug.test_spoil_macro_f1.mean.toFixed(3)} (−${Math.abs(F.ablation_pairs.day_minus_session_aug.mean).toFixed(3)}, 3 seeds)`,
  "Strong noise lowers spoilage macro-F1 to ~0.78–0.80; produce type stays ≥0.96", "3×3 median filter repairs salt-and-pepper noise; DnCNN helps under heavy noise only",
  "Real TR-6 sensor noise (σ≈0.003) is far below these stress levels"], 8.5, 1.5, 4.3, 5.3, 14);

// 10 XAI
pres.addSection({ title: "Explainability" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Explainability" });
s.addText("XAI: attention rollout shows the model looks at the fruit", { placeholder: "title" });
fitImage(s, "xai_class_gallery_part2.png", 0.6, 1.35, 6.3, 2.7, "Correct predictions");
fitImage(s, "xai_failure_fn.png", 0.6, 4.15, 6.3, 2.7, "False negatives");
const xf = F.xai.faithfulness, xs = F.xai.stability;
stat(s, 7.3, 1.5, 2.6, (xf.mean_drop_top_rollout / xf.mean_drop_random).toFixed(0) + "×", "larger confidence drop when highlighted patches are masked vs random");
stat(s, 10.1, 1.5, 2.6, xs.flip_consistency.mean.toFixed(2), "map stability under flip (Spearman ρ)");
bullets(s, ["Missed 'Spoiled' gooseberries look fresh, and attention is on the fruit — the date-based label precedes visible decay",
  "Bright background dots are a known ViT artefact, not evidence of background use", "Explanations are diagnostic, not proof of correctness"], 7.3, 3.3, 5.4, 3.5, 14);

// 11 Additional components
pres.addSection({ title: "New components" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "New components" });
s.addText("Added: visible-decay check, pilot U-Net, proxy shelf-life", { placeholder: "title" });
fitImage(s, "unet_pilot_overlays.png", 0.6, 1.35, 7.0, 3.7, "Pilot U-Net examples");
caption(s, "Pilot U-Net on held-out test images: input / machine mask / prediction", 0.6, 5.1, 7.0);
s.addTable([
  [{ text: "Component", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }, { text: "Held-out result", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }, { text: "Trained on", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }],
  ["Visible-decay check", `${VD.probe_test.accuracy.toFixed(3)} accuracy (n=${VD.probe_test.n})`, "165 human labels"],
  ["Pilot U-Net", `fruit Dice ${UP.mean.fruit_dice.toFixed(2)}, decay Dice ${UP.mean.decay_dice.toFixed(2)}`, "machine masks (pilot)"],
  ["Proxy shelf-life", `MAE ${SL.test.mae_days.toFixed(1)} days, R² ${SL.test.r2.toFixed(2)}`, "days to 'Spoiled' label"]],
  { x: 7.9, y: 1.4, w: 4.9, colW: [1.55, 1.85, 1.5], fontSize: 12, fontFace: "Calibri", color: HEX.dk1, border: { type: "solid", pt: 0.5, color: "C9D6CD" }, rowH: 0.6 });
s.addText(`Human annotation of 180 images: TR-6 'Spoiled' images showed visible decay in only ${VD.dataset_label_vs_human.spoiled_labelled_with_visible_decay}. The U-Net is a pilot (machine-generated masks) and shelf-life is a proxy — both labelled as such in the UI.`,
  { x: 7.9, y: 4.2, w: 4.9, h: 2.4, fontSize: 14, color: C.text1, isTextBox: true });

// 12 Integration
pres.addSection({ title: "Integration and testing" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Integration and testing" });
s.addText("Live integration with the trained models", { placeholder: "title" });
const steps = ["Upload photo (JPG/PNG/WEBP ≤15 MB)", "Validate, decode, EXIF-correct, resize", "ViT-B/16 + visible-decay + U-Net + shelf-life", "Card: type, spoilage, decay %, shelf-life, heat-map", "Saved to SQLite history and dashboard"];
steps.forEach((t, i) => {
  const y = 1.5 + i * 1.0;
  s.addShape(pres.shapes.OVAL, { x: 0.6, y, w: 0.6, h: 0.6, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "step" });
  s.addText(String(i + 1), { x: 0.6, y, w: 0.6, h: 0.6, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  s.addText(t, { x: 1.4, y, w: 5.2, h: 0.6, fontSize: 16, color: C.text1, valign: "middle", isTextBox: true, margin: 0 });
});
const E = F.tests.e2e;
stat(s, 7.2, 1.5, 2.7, `${E.produce_correct}/${E.held_out_images_via_api}`, "produce correct via live API (held-out originals)");
stat(s, 10.1, 1.5, 2.7, `${E.spoilage_correct}/${E.held_out_images_via_api}`, "spoilage correct via live API");
stat(s, 7.2, 3.25, 2.7, Math.round(F.tests.latency.median_ms) + " ms", "median end-to-end latency");
stat(s, 10.1, 3.25, 2.7, `${F.tests.ui_contract.fields_present}/${F.tests.ui_contract.fields_checked}`, "UI fields present in real responses");
s.addText("Errors handled: wrong type (415), corrupt (400), too large (413), model missing (503) — all shown clearly in the UI.",
  { x: 7.2, y: 5.05, w: 5.6, h: 1.2, fontSize: 14, color: C.text1, isTextBox: true });

// 13 Testing
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Integration and testing" });
s.addText("Testing: automated, end-to-end and in the browser", { placeholder: "title" });
const npass = (F.tests.pytest_summary.match(/(\d+) passed/) || [0, "?"])[1];
stat(s, 0.6, 1.5, 2.9, npass, "pytest: API, real model, data integrity");
stat(s, 3.7, 1.5, 2.9, "7", "Vitest: frontend API client + components");
stat(s, 6.8, 1.5, 2.9, `${E.passed}/${E.total}`, "live end-to-end checks passed");
stat(s, 9.9, 1.5, 2.9, "0", "duplicate / session leakage across splits");
bullets(s, ["Missing checkpoint fails clearly (503) — no fabricated predictions", "Mock mode off by default and labelled DEMO MOCK DATA", "Source dataset re-hashed: unchanged", "CORS restricted to the configured frontend origin", "Preprocessing parity: API vs training cache"], 0.6, 3.4, 6.0, 3.3, 15);
fitImage(s, "api_latency.png", 6.9, 3.3, 5.9, 3.4, "API latency");

// 14 Limitations + next steps
pres.addSection({ title: "Conclusion" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Conclusion" });
s.addText("Limitations and next steps", { placeholder: "title" });
const cols = [["Limitations", ["Same physical fruits appear in train and test (no specimen IDs)", "Spoilage labels are date-based; some 'Spoiled' fruit looks fresh", "Lab photos on plain backgrounds; real phone photos untested", "U-Net is a pilot; shelf-life is a proxy"]],
  ["Next steps", ["Human-drawn decay polygons → validated U-Net", "Real-world photo test set", "Confidence calibration", "Third-party deployment (backend ~1.5 GB RAM)", "IEEE DataPort submission of TR-6+"]]];
cols.forEach(([t, items], i) => {
  const x = 0.6 + i * 6.25;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.5, w: 5.9, h: 5.2, rectRadius: 0.12, fill: { color: i ? "EAF1EC" : "FBEDE6" }, line: { color: i ? "EAF1EC" : "FBEDE6" }, objectName: "col" });
  s.addText(t, { x: x + 0.3, y: 1.7, w: 5.3, h: 0.6, fontSize: 22, bold: true, color: i ? C.accent1 : C.accent2, fontFace: THEME.headFontFace, isTextBox: true, margin: 0 });
  bullets(s, items, x + 0.3, 2.45, 5.3, 4.1, 16);
});

// 15 Closing
s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Conclusion" });
s.addText("A real, tested and explainable produce-spoilage prototype", { placeholder: "title" });
s.addText(`ViT-B/16 test spoilage macro-F1 ${f3(TS.macro_f1)} · integrated FastAPI + React app · GAN, XAI, ablation and robustness evaluated · thank you — questions?`, { placeholder: "body" });

pres.writeFile({ fileName: out }).then(async () => { await applyTheme(out, THEME); console.log("wrote", out); });
