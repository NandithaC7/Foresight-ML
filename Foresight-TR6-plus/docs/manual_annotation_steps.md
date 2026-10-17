# Exact Manual Annotation Work

Local Label Studio is the human annotation tool. Python masks are proposals only.

Use `docs/calibration_label_studio_guide.md` for the 12-image calibration batch.

## Step 1: Review before annotation

Open:

- `reports/pilot_review_srgb.jpg`
- `reports/pilot_review_thermal_ir_fusion.jpg`
- `reports/pilot_visual_review.md`
- `docs/annotation_protocol.md`

Confirm that the proposed fruit-mask task is useful and that thermal boundaries are sufficiently interpretable.

## Step 2: Configure the annotation tool

For Label Studio, create a project using `imports/label_studio_config.xml`.

The task JSON uses URLs of the form:

`/data/local-files/?d=TR-6/<relative-path>`

Configure Label Studio local-file serving with its document root set to:

`/Users/nandu/Downloads/foresight`

This lets the tool read TR-6 in place without copying it. Do not configure upload or cloud storage.

## Step 3: Annotate the 12-image calibration batch

Import `imports/calibration_label_studio_tasks.json`.

For each image:

1. Set image disposition to `annotatable`, `ambiguous` or `exclude`.
2. If annotatable, draw `fruit_visible_region`.
3. Draw `visible_defect_region` only when a localized physical boundary is visually defensible.
4. Add notes for every ambiguous or excluded image.
5. Do not assign a spoilage label.

Record completion in `annotations/annotation_records.csv` by changing only the relevant calibration rows from `pending` to `annotated` and recording the annotator and annotation file.

## Step 4: Calibration review

A reviewer must inspect all 12 images at native resolution:

- Correct background/shadow exclusion.
- Consistent stem and calyx handling.
- Boundary quality.
- Defect regions not confused with normal pigmentation, thermal variation or glare.
- Appropriate ambiguous/excluded decisions.

Update accepted rows to `reviewed`. Document disagreements in `notes`.

## Step 5: Validate calibration export

Export COCO segmentation JSON to `annotations/coco_annotations.json`, preserving the template image IDs and category IDs:

- `1`: `fruit_visible_region`
- `2`: `visible_defect_region`

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_extension.py \
  --dataset ../TR-6 \
  --workspace . \
  --hash-mode pilot
```

Resolve validation errors before continuing.

## Step 6: Complete the remaining 84 pilot images

After calibration approval, import `imports/label_studio_tasks.json` or the remaining-task subset created by the annotation tool.

- Complete fruit masks on all annotatable images.
- Keep defect masks conditional.
- Double-annotate at least 20 images balanced across produce and modality.
- Review every defect, ambiguity and exclusion plus at least 20% of routine fruit masks.
- Record all statuses and reasons.

## Step 7: Stop before scaling

After all 96 records are `reviewed` or `excluded`, run validation and calculate QC agreement. Do not select more images until the pilot’s exclusion rate, ambiguity rate, fruit-mask agreement and defect-label agreement have been reviewed and scaling is explicitly approved.
