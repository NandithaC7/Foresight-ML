# TR-6 Multimodal Dataset Audit

Generated: 2026-10-15T17:54:42.256009

Dataset (read only): `/Users/nandu/Downloads/foresight/dataset/TR-6`

## Executive summary

- Inventoried **21,653 files** totaling **19.77 GiB**.
- Validated **21,626 images** incrementally with Pillow `verify()`; found **0 corrupt/invalid**, **0 unreadable**, and **0 zero-byte files**.
- Parsed **18 methane files** containing **26,928 measurement records**.
- SHA-256 hashing found **10,589 exact duplicate groups**, involving **21,439 files** and **10,850 excess copies**.
- Every one of the **10,796 classified images** is an exact byte duplicate of an image in `Normal`; **187** unique Normal image hashes are not represented in `Classified`.
- **170 exact image-content groups occur under both `Spoiled` and `Not_spoiled`**, creating direct label conflicts.
- No RGB↔thermal or image↔methane pairing is verified at specimen level. Filename timestamps and daily ordering provide candidates, not ground truth.
- `Classified` is a labeled derivative structure; `Normal` has no `Spoiled`/`Not_spoiled` path label. These trees must not be treated as independent datasets.

## Inventory by apparent modality

| Modality | Files | Bytes |
| --- | --- | --- |
| documentation | 1 | 1481 |
| metadata_or_other | 8 | 49184 |
| methane | 18 | 1655118 |
| srgb | 10676 | 20279805216 |
| thermal_ir_fusion | 10950 | 941163419 |

Full path-level and directory-level sizes are in `file_inventory.csv` and `directory_summary.csv`.

## Actual directory semantics and class distributions

`Normal/<produce>/{IR_fusion_images,sRGB_images}` contains modality folders plus one produce-level methane file. `Classified/<produce>/{Not_spoiled,Spoiled}/{IR_fusion_images,sRGB_images}` adds path-based spoilage labels and one methane file per label. The README describes the same concepts but states the nesting order ambiguously.

| Tree | Produce | Path label | Modality | Files |
| --- | --- | --- | --- | --- |
| Classified | Banana | Not_spoiled | methane | 1 |
| Classified | Banana | Not_spoiled | srgb | 153 |
| Classified | Banana | Not_spoiled | thermal_ir_fusion | 153 |
| Classified | Banana | Spoiled | methane | 1 |
| Classified | Banana | Spoiled | srgb | 170 |
| Classified | Banana | Spoiled | thermal_ir_fusion | 153 |
| Classified | Carrot | Not_spoiled | methane | 1 |
| Classified | Carrot | Not_spoiled | srgb | 102 |
| Classified | Carrot | Not_spoiled | thermal_ir_fusion | 103 |
| Classified | Carrot | Spoiled | methane | 1 |
| Classified | Carrot | Spoiled | srgb | 356 |
| Classified | Carrot | Spoiled | thermal_ir_fusion | 355 |
| Classified | Guava | Not_spoiled | methane | 1 |
| Classified | Guava | Not_spoiled | srgb | 204 |
| Classified | Guava | Not_spoiled | thermal_ir_fusion | 212 |
| Classified | Guava | Spoiled | methane | 1 |
| Classified | Guava | Spoiled | srgb | 306 |
| Classified | Guava | Spoiled | thermal_ir_fusion | 306 |
| Classified | Indian_Gooseberry | Not_spoiled | methane | 1 |
| Classified | Indian_Gooseberry | Not_spoiled | srgb | 884 |
| Classified | Indian_Gooseberry | Not_spoiled | thermal_ir_fusion | 903 |
| Classified | Indian_Gooseberry | Spoiled | methane | 1 |
| Classified | Indian_Gooseberry | Spoiled | srgb | 527 |
| Classified | Indian_Gooseberry | Spoiled | thermal_ir_fusion | 525 |
| Classified | Mango | Not_spoiled | methane | 1 |
| Classified | Mango | Not_spoiled | srgb | 256 |
| Classified | Mango | Not_spoiled | thermal_ir_fusion | 255 |
| Classified | Mango | Spoiled | methane | 1 |
| Classified | Mango | Spoiled | srgb | 136 |
| Classified | Mango | Spoiled | thermal_ir_fusion | 152 |
| Classified | Tomato | Not_spoiled | methane | 1 |
| Classified | Tomato | Not_spoiled | srgb | 2074 |
| Classified | Tomato | Not_spoiled | thermal_ir_fusion | 2137 |
| Classified | Tomato | Spoiled | methane | 1 |
| Classified | Tomato | Spoiled | srgb | 170 |
| Classified | Tomato | Spoiled | thermal_ir_fusion | 204 |
| Normal | Banana | unlabeled | methane | 1 |
| Normal | Banana | unlabeled | srgb | 323 |
| Normal | Banana | unlabeled | thermal_ir_fusion | 340 |
| Normal | Carrot | unlabeled | methane | 1 |
| Normal | Carrot | unlabeled | srgb | 458 |
| Normal | Carrot | unlabeled | thermal_ir_fusion | 458 |
| Normal | Guava | unlabeled | methane | 1 |
| Normal | Guava | unlabeled | srgb | 510 |
| Normal | Guava | unlabeled | thermal_ir_fusion | 518 |
| Normal | Indian_Gooseberry | unlabeled | methane | 1 |
| Normal | Indian_Gooseberry | unlabeled | srgb | 1411 |
| Normal | Indian_Gooseberry | unlabeled | thermal_ir_fusion | 1428 |
| Normal | Mango | unlabeled | methane | 1 |
| Normal | Mango | unlabeled | srgb | 392 |
| Normal | Mango | unlabeled | thermal_ir_fusion | 407 |
| Normal | Tomato | unlabeled | methane | 1 |
| Normal | Tomato | unlabeled | srgb | 2244 |
| Normal | Tomato | unlabeled | thermal_ir_fusion | 2341 |

Only `Classified` supplies a defensible existing binary path label. `Normal` should be treated as unlabeled with respect to spoilage unless a documented derivation map is supplied.

## Image audit

- Apparent sRGB files: **10,676**.
- Apparent thermal IR-fusion files: **10,950**.
- Modality identification is based on the explicit directory names and README, not pixel appearance alone.
- Thermal filenames include two temperature-like values with `C`; their precise meanings are not documented.
- All thermal images are 640×480 RGB JPEG renderings. sRGB images are RGB JPEGs: predominantly 4000×3000, with a 2576×1932 subset.
- Across both trees, sRGB file sizes have median **1750.4 KiB** (p95 **2976.1 KiB**); thermal files have median **83.7 KiB** (p95 **87.1 KiB**).
- Detailed dimensions, formats, color modes, and size percentiles are in `image_summary.csv`.
- One median-path sample from every source/produce/label/modality stratum is recorded in `representative_image_samples.csv`; visual contact sheets are alongside this report.

## Methane audit

The files are structured text, not CSV. Measurement lines contain four pipe-separated labeled fields: ADC, sensor resistance `Rs` in kΩ, `Rs/R0`, and methane in ppm. Hierarchical headers encode `Day`, `case`, and side `R`/`L`. No wall-clock timestamp, sampling interval, specimen UUID, device ID, calibration record, environmental measurement, or explicit link to image filenames is present.

| Tree | Produce | Path label | Records | Days | Null markers | Malformed measurement lines |
| --- | --- | --- | --- | --- | --- | --- |
| Classified | Banana | Not_spoiled | 341 | 1;2;3 | 1 | 0 |
| Classified | Banana | Spoiled | 506 | 4;5;6;7 | 0 | 0 |
| Classified | Carrot | Not_spoiled | 151 | 1;2 | 0 | 0 |
| Classified | Carrot | Spoiled | 698 | 3;4;5;6;7;8 | 0 | 0 |
| Classified | Guava | Not_spoiled | 830 | 1;2;3;4 | 0 | 0 |
| Classified | Guava | Spoiled | 1289 | 5;6;7;8;9;10 | 0 | 0 |
| Classified | Indian_Gooseberry | Not_spoiled | 1816 | 1;2;3;4;5;6;7;8;9;10;11;12;13;14;15;16;17;18 | 1 | 2 |
| Classified | Indian_Gooseberry | Spoiled | 1273 | 19;20;21;22;23;24;25;26;27;28;29;30;31 | 5 | 0 |
| Classified | Mango | Not_spoiled | 688 | 1;2;3;4 | 0 | 0 |
| Classified | Mango | Spoiled | 447 | 5;6;7 | 0 | 0 |
| Classified | Tomato | Not_spoiled | 4860 | 1;2;3;4;5;6;7;8;9;10;11;12;13;14;15;16;17;18;19;20;21;22;23;24;25;26;27;28;29;30;31;32;33;34;35;36;37;38;39;40;41;42;43;44 | 5 | 0 |
| Classified | Tomato | Spoiled | 565 | 45;46;47;48 | 0 | 1 |
| Normal | Banana | unlabeled | 847 | 1;2;3;4;5;6;7 | 1 | 0 |
| Normal | Carrot | unlabeled | 849 | 1;2;3;4;5;6;7;8 | 0 | 0 |
| Normal | Guava | unlabeled | 2119 | 1;2;3;4;5;6;7;8;9;10 | 0 | 0 |
| Normal | Indian_Gooseberry | unlabeled | 3089 | 1;2;3;4;5;6;7;8;9;10;11;12;13;14;15;16;17;18;19;20;21;22;23;24;25;26;27;28;29;30;31 | 6 | 2 |
| Normal | Mango | unlabeled | 1135 | 1;2;3;4;5;6;7 | 0 | 0 |
| Normal | Tomato | unlabeled | 5425 | 1;2;3;4;5;6;7;8;9;10;11;12;13;14;15;16;17;18;19;20;21;22;23;24;25;26;27;28;29;30;31;32;33;34;35;36;37;38;39;40;41;42;43;44;45;46;47;48 | 5 | 1 |

`methane_files.csv` reports value ranges, missing/null markers, malformed lines, and per-file structure. Three representative parsed records per file are in `methane_sample_records.csv`; exact issue locations are in `methane_issues.csv`. Across `Normal`, 12 `-null-` markers and three malformed measurement lines were found; the same issues recur in their classified text spans. Repeated consecutive values are common but are retained as observations; measurement frequency cannot be inferred without timestamps or acquisition documentation.

## Multimodal correspondence

| Tree | Produce | Path label | RGB | Thermal | Exact timestamp candidates | Mutual nearest ≤120 s |
| --- | --- | --- | --- | --- | --- | --- |
| Classified | Banana | Not_spoiled | 153 | 153 | 0 | 1 |
| Classified | Banana | Spoiled | 170 | 153 | 0 | 0 |
| Classified | Carrot | Not_spoiled | 102 | 103 | 0 | 2 |
| Classified | Carrot | Spoiled | 356 | 355 | 0 | 6 |
| Classified | Guava | Not_spoiled | 204 | 212 | 0 | 7 |
| Classified | Guava | Spoiled | 306 | 306 | 0 | 13 |
| Classified | Indian_Gooseberry | Not_spoiled | 884 | 903 | 0 | 21 |
| Classified | Indian_Gooseberry | Spoiled | 527 | 525 | 0 | 3 |
| Classified | Mango | Not_spoiled | 256 | 255 | 0 | 10 |
| Classified | Mango | Spoiled | 136 | 152 | 0 | 0 |
| Classified | Tomato | Not_spoiled | 2074 | 2137 | 3 | 68 |
| Classified | Tomato | Spoiled | 170 | 204 | 0 | 0 |
| Normal | Banana | unlabeled | 323 | 340 | 0 | 2 |
| Normal | Carrot | unlabeled | 458 | 458 | 0 | 8 |
| Normal | Guava | unlabeled | 510 | 518 | 0 | 20 |
| Normal | Indian_Gooseberry | unlabeled | 1411 | 1428 | 0 | 24 |
| Normal | Mango | unlabeled | 392 | 407 | 0 | 10 |
| Normal | Tomato | unlabeled | 2244 | 2341 | 3 | 68 |

### Verified

- Exact byte identity established by SHA-256 is verified only for duplicate files.
- `methane_normal_classified_correspondence.csv` tests whether each classified methane file is an exact text span of its produce-level Normal file.
- `classified_normal_exact_duplicates.csv` quantifies exact image/file reuse from `Normal` into `Classified`.

| Produce | Label | Modality | Exact Normal duplicates | Classified files |
| --- | --- | --- | --- | --- |
| Banana | Not_spoiled | methane | 0 | 1 |
| Banana | Not_spoiled | srgb | 153 | 153 |
| Banana | Not_spoiled | thermal_ir_fusion | 153 | 153 |
| Banana | Spoiled | methane | 0 | 1 |
| Banana | Spoiled | srgb | 170 | 170 |
| Banana | Spoiled | thermal_ir_fusion | 153 | 153 |
| Carrot | Not_spoiled | methane | 0 | 1 |
| Carrot | Not_spoiled | srgb | 102 | 102 |
| Carrot | Not_spoiled | thermal_ir_fusion | 103 | 103 |
| Carrot | Spoiled | methane | 0 | 1 |
| Carrot | Spoiled | srgb | 356 | 356 |
| Carrot | Spoiled | thermal_ir_fusion | 355 | 355 |
| Guava | Not_spoiled | methane | 0 | 1 |
| Guava | Not_spoiled | srgb | 204 | 204 |
| Guava | Not_spoiled | thermal_ir_fusion | 212 | 212 |
| Guava | Spoiled | methane | 0 | 1 |
| Guava | Spoiled | srgb | 306 | 306 |
| Guava | Spoiled | thermal_ir_fusion | 306 | 306 |
| Indian_Gooseberry | Not_spoiled | methane | 0 | 1 |
| Indian_Gooseberry | Not_spoiled | srgb | 884 | 884 |
| Indian_Gooseberry | Not_spoiled | thermal_ir_fusion | 903 | 903 |
| Indian_Gooseberry | Spoiled | methane | 0 | 1 |
| Indian_Gooseberry | Spoiled | srgb | 527 | 527 |
| Indian_Gooseberry | Spoiled | thermal_ir_fusion | 525 | 525 |
| Mango | Not_spoiled | methane | 0 | 1 |
| Mango | Not_spoiled | srgb | 256 | 256 |
| Mango | Not_spoiled | thermal_ir_fusion | 255 | 255 |
| Mango | Spoiled | methane | 0 | 1 |
| Mango | Spoiled | srgb | 136 | 136 |
| Mango | Spoiled | thermal_ir_fusion | 152 | 152 |
| Tomato | Not_spoiled | methane | 0 | 1 |
| Tomato | Not_spoiled | srgb | 2074 | 2074 |
| Tomato | Not_spoiled | thermal_ir_fusion | 2137 | 2137 |
| Tomato | Spoiled | methane | 0 | 1 |
| Tomato | Spoiled | srgb | 170 | 170 |
| Tomato | Spoiled | thermal_ir_fusion | 204 | 204 |

### Probable

- RGB and thermal images in the same tree/produce/path-label with identical filename timestamps are probable same-capture candidates.
- Mutual nearest timestamps within 120 seconds on the same date are weaker probable session candidates.
- Timestamp clusters in `inferred_image_sessions.csv` are operational session hypotheses only. Mutual-nearest 17-image RGB/thermal sessions within 30 minutes are listed in `probable_session_correspondence.csv`. Both thresholds are audit heuristics, not annotations or verified pairs.

### Unresolved

- No filename contains a documented specimen/case identifier or view index.
- `case 1..N` and `R/L` in methane text cannot be mapped to particular images.
- The README's statement about 17 thermal images per fruit per day does not prove 17 RGB pairs, and counts are not uniformly equal.
- Sorted dates/days may reflect chronology, but no explicit acquisition-date-to-`Day N` map exists.
- Therefore **zero cross-modal specimen-level pairs are marked verified**.

## Duplication, leakage, and split risks

- Exact duplicates across `Normal` and `Classified` make those trees non-independent.
- The **170** exact duplicate groups crossing `Spoiled` and `Not_spoiled` are direct label conflicts. They comprise all 153 Banana thermal images in each label plus 17 Indian Gooseberry thermal contents.
- Images within short timestamp clusters are repeated views of one collection event and likely of the same produce specimen. Random image-level splitting would leak appearance, background, date, device, and maturity trajectory.
- Consecutive days are temporally dependent. Splitting adjacent days for the same specimen across train/test would overstate generalization.
- Filename temperatures and thermal rendering may encode acquisition conditions correlated with labels.

## Research readiness

- **Potentially suitable after conflict exclusion and provenance review:** produce-type classification, and exploratory path-label spoilage classification using `Classified`. The binary label is not publication-ready while identical images carry conflicting labels.
- **Not currently supported:** segmentation and object detection (no masks/boxes), shelf-life regression (no verified remaining-life target), specimen-level multimodal fusion (no defensible cross-modal key), or calibrated methane-based spoilage inference (no protocol/calibration metadata).
- A leakage-safe split cannot yet be guaranteed at specimen level. Until specimen IDs are recovered, group all exact duplicates together, then group by produce plus conservative timestamp-session/date blocks; keep an entire inferred longitudinal date range together where it may represent one specimen. Use leave-one-specimen/session-out only after provenance confirms those groups.

## Proposed Foresight-TR6+ extension

1. Recover acquisition logs and assign immutable `specimen_id`, `session_id`, `capture_id`, `view_id`, device IDs, and timezone-aware timestamps.
2. Create a reviewed manifest linking RGB, thermal, and methane windows with confidence and provenance; preserve unmatched records.
3. Record ground-truth spoilage assessment protocol, assessor agreement, maturity stage, storage conditions, acquisition environment, and label timestamp.
4. Add calibrated thermal data or radiometric metadata if available; document the two filename temperatures.
5. Add methane sensor model, calibration curve/R0 procedure, warm-up time, sampling rate, chamber geometry, background baseline, temperature, and humidity.
6. For a defensible new task, annotate fruit masks and visible-defect regions on a specimen/session-stratified subset with inter-annotator quality control.
7. For shelf-life regression, collect actual time-to-defined-endpoint prospectively; do not derive it solely from folder labels or methane magnitude.
8. Publish checksums, a data dictionary, lineage from TR-6 to TR6+, annotation guidelines, adjudication records, exclusions, and leakage-safe official splits.

## Questions required before annotation or IEEE DataPort publication

1. What exactly do `Normal`, `Classified`, `Spoiled`, and `Not_spoiled` mean, and who assigned the labels using what criterion?
2. Are the `Classified` files intended to be a partitioned copy of `Normal`, and were any files omitted or duplicated intentionally?
3. How many physical specimens exist per produce, and does methane `case N` identify a specimen, container, replicate, or sensor run?
4. What do methane sides `R` and `L` mean?
5. Which calendar date corresponds to each `Day N`, and what is the sampling interval?
6. How are 17 views ordered, which is top-down, and are RGB and thermal captures simultaneous or sequential?
7. What do the two temperatures in thermal filenames represent?
8. Are thermal JPGs radiometric, rendered fusion images, or both? Is raw thermal data available?
9. What camera/sensor models, settings, calibration, distance, lighting, background, storage conditions, temperature, and humidity were used?
10. Are filename timestamps reliable and in one timezone? Were clocks synchronized?
11. Is there consent/licensing provenance and a publication-ready data license?
12. What exclusion criteria, missing-data policy, and intended benchmark task should the official release specify?

## Assumptions and limitations

- Directory names are used as apparent modality and existing label metadata.
- Filename timestamps are parsed as local naive times because no timezone is documented.
- Image validity means Pillow could parse and verify the encoded file; it is not a semantic-quality score.
- Exact duplication means equal SHA-256 content.
- Visual review uses representative samples, not every image.
- Session clusters and probable matches are deliberately not saved as labels.

## Reproduction

See `commands.txt`. The script reads the dataset and writes only to the separate audit output directory.
