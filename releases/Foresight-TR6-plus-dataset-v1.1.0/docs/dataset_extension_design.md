# Foresight-TR6+ Phase 1 Design

Status: pilot workspace prepared; manual annotations not started.

## Objective

Foresight-TR6+ will add provenance-aware manifests and human-reviewed visible-region annotations without changing TR-6, asserting unsupported spoilage labels or inventing multimodal correspondence.

## Inherited from TR-6

- sRGB JPEG images.
- Thermal IR-fusion JPEG renderings.
- Methane structured-text measurements.
- Six produce directory names.
- `Spoiled` and `Not_spoiled` directory labels in `Classified`.
- Filename timestamps and thermal filename values.

Every inherited field is marked by origin and verification status. Classified spoilage labels remain inherited and independently unverified. Normal-tree records remain spoilage-unlabeled.

## Inherited from the completed audit

- Relative paths, sizes and SHA-256 hashes.
- File readability and image validity.
- Image dimensions, formats and apparent modalities.
- Duplicate groups and cross-label conflicts.
- Evidence that Classified images are exact copies of Normal images.
- Evidence that classified methane files are exact text spans of Normal methane files.

The audit is not repeated by this phase; its machine-readable outputs are transformed reproducibly by `scripts/build_extension.py`.

## New contribution planned

1. A provenance-aware master manifest covering all original file records.
2. Content-stable identifiers and explicit duplicate/conflict metadata.
3. A balanced 96-image pilot across six produce types and two modalities.
4. Human fruit-visible-region masks for annotatable pilot images.
5. Conditional visible-defect-region masks only where boundaries are defensible.
6. Annotation status, reviewer decisions, exclusions and QC measurements.
7. Reproducible validation and release documentation.

Only items 1–3 and the empty annotation infrastructure are complete in Phase 1. No masks or defect ground truth have been created.

## Pilot design

The pilot selects eight images for each produce × modality stratum, for 96 images total. Selection uses:

- Canonical content from the Normal tree.
- Exact-hash deduplication.
- Exclusion of every cross-label conflict hash.
- Deterministic seed `20261012`.
- Dimension-aware and date-diverse deterministic selection.
- No inherited spoilage labels.

The pilot intentionally tests annotation feasibility on both visible and thermal renderings. Visible-defect annotation is expected to be more defensible on sRGB. Thermal defect polygons are optional and should usually remain absent unless the physical boundary is visible without cross-modal inference.

## Why segmentation first

Fruit foreground masks are directly observable in most reviewed images and support segmentation, background-control studies and future multimodal registration research without claiming spoilage truth. Visible-defect masks can add scientific value, but only for localized, visually bounded regions; they must not be forced on every image.

Object detection boxes would add little when a single centered produce item dominates most frames. Shelf-life regression is unsupported because no verified remaining-life target exists. Spoilage classification remains blocked by label conflicts and undocumented provenance.

## Leakage controls

- One pilot record per exact content hash.
- Cross-label conflict hashes excluded.
- Normal and Classified copies never treated as independent.
- Future train/validation/test splits must group all views and dates from the same confirmed specimen.
- Until specimen provenance exists, no official model benchmark split should be published.

## Phase completion criteria

Phase 1 is complete when manifests and templates validate, pilot hashes match source files, no conflict hash enters the pilot, and all annotation records remain explicitly `pending`.

The next phase requires manual annotation, calibration review, double annotation, adjudication and QC reporting. Scaling beyond the pilot requires explicit approval.
