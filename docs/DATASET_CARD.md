# Dataset card — TR-6 as used by Foresight (split v1)

Status: **MEASURED** (every count below was recomputed from files on 2026-10-15)

## Source
- **TriModal Ripeness 6 (TR-6)**, by T Bagyammal, Yogini Aishwaryaa P T S, Krishna Deepak and Devika Unnikrishnan (2025). It is on Figshare with DOI 10.6084/m9.figshare.30783827.v1.
- The licence is **CC BY 4.0**, as recorded from the Figshare API in `Foresight-TR6-plus/publication/LICENSE_AND_ATTRIBUTION.md`. Attribution is required.
- The local copy is `dataset/TR-6/`. It was treated as **read-only**. A sample of originals is re-hashed in `ml/tests/test_ml.py::test_source_files_unchanged`.

## Audit re-run (2026-10-15)
- Command: `audit_tr6.py --dataset dataset/TR-6 --output dataset-preparation/tr6-audit/output_rerun_2026-10-15`. It ran in 15.9 s.
- The result is **identical** to the prior audit (2026-10-12) on every summary field. The only change is the dataset path, which moved from `TR-6/` to `dataset/TR-6/`.

| Item | Value |
|---|---|
| Files | 21,653 (19.77 GiB) |
| Valid JPEGs | 21,626 (10,676 sRGB, 10,950 thermal IR-fusion); 0 corrupt |
| Methane logs | 18 files |
| Unique image contents (SHA-256) | 10,776 |
| Exact-duplicate groups | 10,589 (10,850 excess copies) |
| Classified images byte-identical to a Normal image | 10,796 (all of them) |
| Cross-label duplicate groups (same bytes under both Spoiled and Not_spoiled) | 170, all thermal: 153 Banana and 17 Indian Gooseberry |
| Verified RGB↔thermal or image↔methane pairs | 0 |

## Label policy
- **Produce type** comes from the folder name (6 classes). It is consistent for every content.
- **Spoilage** comes from the `Classified/{Spoiled,Not_spoiled}` folder label. Its `label_status` is `dataset_provided_folder_label`, and it was **not independently verified**.
  The labels follow capture date for each produce: earlier days are Not_spoiled and later days are Spoiled.
- `Normal/` has no spoilage label, so those contents are `unlabeled`. All sRGB Normal images duplicate a Classified image anyway.
- **Conflicts**: a content that appears under both labels is `inherited_conflicting` and is excluded. It is not tie-broken (170 contents, listed in `artifacts/dataset/v1/conflicting_labels.csv`).
- **Modality scope**: the deployed app receives phone RGB photos, so the model uses **sRGB only**. Thermal contents are kept in the manifest but excluded with the reason `modality_out_of_scope_thermal`.
- There are no shelf-life targets, and none were invented. Specimen IDs are blank because TR-6 does not provide them.

## Eligible set and exclusions (unique contents)
| | count |
|---|---|
| Unique image contents | 10,776 |
| Excluded: thermal (out of scope) | 5,084 |
| Excluded: conflicting spoilage labels | 170 |
| Excluded: Normal-only, no spoilage label | 187 |
| **Eligible sRGB samples** | **5,335** |

## Split (seed 42) — `artifacts/dataset/v1/split_manifest.csv`
- The grouping unit is the **inferred capture session**: same produce/label folder, filename timestamps ≤300 s apart on the same date. A session is usually 17 views of one fruit.
  Sessions are shuffled within each produce×label stratum and assigned 60/20/20 by session count. The split was made **before** any augmentation.
- Train has **3,177** images (59.55%) in 189 sessions, validation **1,087** (20.37%) in 64 sessions, and test **1,071** (20.07%) in 64 sessions.
- Leakage checks (`split_summary.json`): 0 content hashes in more than one split, and 0 sessions in more than one split.
- Re-running the script reproduces a **byte-identical** manifest.

| produce / label | train | val | test |
|---|---|---|---|
| Banana / Not_spoiled | 85 | 34 | 34 |
| Banana / Spoiled | 102 | 34 | 34 |
| Carrot / Not_spoiled | 68 | 17 | 17 |
| Carrot / Spoiled | 220 | 68 | 68 |
| Guava / Not_spoiled | 117 | 50 | 35 |
| Guava / Spoiled | 170 | 68 | 68 |
| Indian Gooseberry / Not_spoiled | 544 | 170 | 170 |
| Indian Gooseberry / Spoiled | 323 | 102 | 102 |
| Mango / Not_spoiled | 154 | 51 | 51 |
| Mango / Spoiled | 68 | 34 | 34 |
| Tomato / Not_spoiled | 1,224 | 425 | 424 |
| Tomato / Spoiled | 102 | 34 | 34 |

## Known limitations (disclosed, not fixed)
1. **Specimen leakage is unavoidable.** Each produce is a small number of specimens photographed about 3× a day for days, so train and test contain the same physical fruit.
2. **Same-day proximity.** 49 of the 64 test sessions share a produce and calendar day with a training session.
   A stricter **day-grouped** split (`artifacts/dataset/v1_daygroup_sensitivity/`, sizes 3,076 / 1,138 / 1,121) leaves only 2 shared days, both from Carrot/Not_spoiled, which has 2 dates and falls back to session grouping.
   That split is used only for a sensitivity analysis (Table T8).
3. **Label semantics.** Spoiled/Not_spoiled is a date-based folder label. A model can partly learn day-specific cues such as lighting or background, as well as genuine decay.
4. **Imbalance.** Tomato/Not_spoiled is 39% of the eligible data. Macro-F1 is therefore the primary metric.
5. **Domain.** Every image is a single fruit on a plain light background in lab lighting. Real phone photos are out of distribution and have not been evaluated.

## Derived data
- `artifacts/cache/srgb_256/` holds EXIF-orientation-corrected, shorter-side-256 JPEG copies used for training (`cache_info.json`). They are derived data and are not for redistribution.
- `artifacts/experiments/gan/generated/` holds synthetic images. They are marked `synthetic_cdcgan_train_only`, were never used for validation or test, and are never counted as observations.
- Corrupted test images are generated **in memory** with a deterministic seed per image and corruption, and are never written to disk.
