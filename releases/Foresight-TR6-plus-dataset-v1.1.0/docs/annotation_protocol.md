# Foresight-TR6+ Pilot Annotation Protocol

Version: 0.1.1 pilot  
Status: 12-image calibration pending human Label Studio annotation. Python masks are `proposal_only`, not ground truth.

## Scope

The 96-image pilot evaluates whether consistent visible-region annotations can be produced across six produce types and two apparent modalities. It is not a spoilage-labeling exercise and does not establish multimodal correspondence.

Each pilot image has a stable `pilot_id`, content-based identifier, SHA-256 hash and relative source path in `manifests/pilot_manifest.csv`. Original images remain in TR-6.

## Annotation classes

### 1. `fruit_visible_region`

Required for every annotatable image.

Annotate the visible pixels belonging to the target fruit or vegetable. Include:

- Intact skin and flesh belonging to the produce.
- Naturally attached stem, calyx or crown when clearly part of the specimen.
- Visible damaged, darkened or spoiled areas that remain part of the produce.
- Holes fully enclosed by the fruit silhouette only when they are genuinely background; otherwise keep the fruit region continuous.

Exclude:

- Background, table, wall, tray, ruler or support.
- Cast shadows and reflections.
- Detached debris or fluid unless its physical attachment to the specimen is clear.
- Text overlays, borders and thermal color legends if present.

Where the outline is blurred or thermally diffuse, place the boundary at the strongest stable transition and mark the image `ambiguous` when uncertainty is substantial.

### 2. `visible_defect_region`

Conditional. Annotate only a localized region that is visually distinguishable from surrounding produce tissue and plausibly represents surface damage or deterioration.

Examples that may qualify:

- Localized mold-like growth.
- Clearly bounded bruising, rot, lesions, cuts or severe discoloration.
- Collapsed or necrotic-looking tissue with a visible boundary.

Do not annotate:

- Normal pigmentation, ripening color, lenticels, stem scars or expected texture.
- Global color change without a defensible local boundary.
- Sensor noise, thermal palette variation, glare or shadow.
- A defect inferred only from the inherited `Spoiled` directory label.
- A thermal hot/cold region unless a visible physical defect boundary can be justified from that image alone.

An image may have a fruit mask and zero defect masks. Absence of a defect polygon means “no confidently delineable visible defect,” not “not spoiled.”

## Mask geometry

- Trace polygons clockwise or counter-clockwise without self-intersection.
- Follow the visible boundary; do not hallucinate occluded contours.
- Multiple disconnected components are separate polygons.
- A defect polygon must lie within a `fruit_visible_region`, except for a one-pixel export-rounding tolerance.
- Use the image’s native pixel coordinates and dimensions.
- Do not resize, crop or rotate source images before annotation.
- Suggested boundary precision: within 3 pixels for 640×480 thermal images and within 8 pixels for high-resolution sRGB images when the edge is clear.

Optional raster exports use:

- `0`: background
- `1`: fruit visible region
- `2`: visible defect region
- `255`: ignore/ambiguous boundary

No raster masks exist at pilot creation time.

## Ambiguous cases

Set `image_quality=ambiguous` and explain why when:

- Fruit and background have insufficient contrast.
- More than one plausible target object is present.
- Cropping removes a large, uncertain portion of the fruit.
- Thermal fusion makes the physical edge uncertain.
- A possible defect cannot be separated from normal texture.

Annotate the fruit only if a repeatable boundary remains possible. Do not force a defect annotation.

## Exclusion criteria

Set status to `excluded` and provide an exclusion reason when:

- The file cannot be decoded at annotation time.
- The target produce is absent or almost entirely outside the frame.
- Severe blur, obstruction or rendering artifacts prevent a defensible fruit mask.
- The wrong produce or an unrelated image is present.
- The image is discovered to be an unresolved exact duplicate already annotated under another pilot ID.
- Provenance review finds that the record must not be used.

Do not exclude merely because no visible defect is present.

## Status workflow

1. `pending`: selected but no human annotation started.
2. `pending_review`: a Python proposal may exist, but human Label Studio annotation is incomplete.
3. `annotated`: a human submitted the image and disposition fields in Label Studio.
4. `reviewed`: a second pass accepted or adjudicated the human annotation.
5. `excluded`: image rejected with a recorded reason.

Proposal fields are separate:

- `proposal_status=proposal_only`: unverified computer-assisted mask kept for comparison.
- `proposal_status=none`: no proposal generated.
- `label_studio_status`: `not_imported`, `unsubmitted`, `submitted`, or `cancelled`.

Python proposals must not be recorded as `annotated` or `reviewed`. Human exports go to `annotations/human_coco_annotations.json`. `annotations/coco_annotations.json` is a proposal archive only.

## Quality control

1. Annotate a calibration batch of 12 images first: one sRGB and one thermal image for each produce type.
2. Review all 12 before continuing. Refine this protocol only through a versioned change note.
3. Double-annotate at least 20 pilot images, balanced across produce and modality.
4. Compare fruit masks using IoU and Dice. Compare defect masks only where both annotators identify a defect; separately report detection disagreement.
5. Target fruit-mask IoU ≥0.90 for clear sRGB images and ≥0.85 for thermal images. These are pilot QC thresholds, not claims about achieved quality.
6. A reviewer checks every defect polygon, every ambiguous image, every exclusion and at least 20% of otherwise routine fruit masks.
7. Resolve disagreements by documented adjudication; never average polygons silently.
8. Run `scripts/validate_extension.py` after exports.

## Prohibited in this phase

- Assigning or correcting spoilage labels from appearance.
- Pairing RGB, thermal and methane records.
- Inferring specimen, view or capture identifiers.
- Copying generated masks into the reviewed set without human verification.
- Treating “no visible defect” as proof of `Not_spoiled`.
