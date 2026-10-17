# Manual annotation work

Local Label Studio is the human annotation tool. Python masks are proposals only.

Use `docs/calibration_label_studio_guide.md` for the 12-image calibration batch.

## Step 1: Review before annotation

Read `docs/annotation_protocol.md` and `annotations/PROPOSAL_ONLY.md`. Contact-sheet JPEGs used in the local workspace are **not** included in this publication package.

## Step 2: Configure the annotation tool

Create a Label Studio project using `imports/label_studio_config.xml`.

Task JSON uses URLs of the form:

`/data/local-files/?d=TR-6/<relative-path>`

Set the Label Studio local-files document root to the **parent directory of your TR-6 copy**. Do not copy TR-6 into Label Studio cloud storage.

## Step 3: Annotate the 12-image calibration batch

Import `imports/calibration_label_studio_tasks.json`.

For each image:

1. Set image disposition to `annotatable`, `ambiguous` or `exclude`.
2. If annotatable, draw `fruit_visible_region`.
3. Draw `visible_defect_region` only when a localized physical boundary is visually defensible.
4. Do not treat Python proposals as accepted annotations.

The remaining 84 pilot images stay `pending` until the calibration batch is human-reviewed.

## Step 4: Export

Write human submissions to `annotations/human_coco_annotations.json` and update the ledger. Proposal COCO stays `proposal_only`.
