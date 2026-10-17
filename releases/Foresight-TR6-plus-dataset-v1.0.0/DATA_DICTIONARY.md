# Data dictionary — Foresight-TR6+ v1.0.0

Every published table is derived from a read-only audit of TriModal Ripeness 6 (TR-6). Original images and methane text files are **not** in this package. Relative paths name files in the Figshare TR-6 tree.

Boolean fields are encoded as `true` / `false` lowercase strings in CSV. Empty cells are unknown or not applicable, not imputed values.

---

## `manifests/master_manifest.csv`

One row per audited TR-6 file (21,653 rows).

| Field | Meaning |
| --- | --- |
| `record_id` | Stable id `tr6r_<sha256 of original_relative_path>`. Identifies a path, not unique content. |
| `content_id` | Stable id `tr6c_<file sha256>`. Equal values mean exact byte identity. |
| `source_dataset` | Always `TR-6`. |
| `original_relative_path` | Path relative to the TR-6 root (POSIX separators). |
| `source_path_relative_to_workspace` | Layout hint `../TR-6/<original_relative_path>`. The file is not included here. |
| `sha256` | SHA-256 of the original file bytes. |
| `size_bytes` | File size in bytes. |
| `extension` | Lowercase suffix, or `[none]`. |
| `source_directory` | `Normal`, `Classified`, or `root`. |
| `produce_type` | `Banana`, `Carrot`, `Guava`, `Indian_Gooseberry`, `Mango`, `Tomato`, or `unknown`. |
| `apparent_modality` | Directory-derived: `srgb`, `thermal_ir_fusion`, `methane`, `documentation`, `metadata_or_other`. Not a pixel classifier. |
| `existing_path_label` | Literal directory label (`Spoiled`, `Not_spoiled`) or `unknown`. |
| `spoilage_label` | Inherited Classified-tree label or `unknown`. Normal remains `unknown`. |
| `label_origin` | `inherited_from_directory_name` or `unavailable`. |
| `label_independently_verified` | Always `false` in this release. |
| `label_status` | `unlabeled`, `inherited_unverified`, or `inherited_conflicting`. |
| `filename_timestamp` | Parsed filename timestamp (`YYYY-MM-DDTHH:MM:SS`) or `unknown`. Timezone-naive. |
| `timestamp_status` | Records that filename time is unverified. |
| `width`, `height` | Stored JPEG pixel size, or `unknown`. sRGB is 4000×3000 as stored (EXIF orientation 6). |
| `image_format`, `color_mode` | Pillow-reported format/mode, or `unknown`. |
| `file_read_status` | Audit read result (`readable`). |
| `file_validation_status` | Image verify result, or `not_applicable`. |
| `duplicate_group_id` | Exact-hash group id (`D#####`) or `none`. |
| `duplicate_member_count` | Number of exact copies in that group. |
| `cross_source_duplicate` | Exact content occurs in both Normal and Classified. |
| `cross_label_conflict` | Exact content occurs under both `Spoiled` and `Not_spoiled`. |
| `canonical_content_reference` | `true` for one deterministic path per `content_id`. This does **not** choose a correct label. |
| `specimen_id`, `capture_id`, `view_id`, `cross_modal_group_id` | Always `unknown`; never inferred. |
| `segmentation_pilot_eligible` | Valid, canonical, conflict-free Normal image eligible for deterministic sampling. |
| `spoilage_supervision_eligible` | `false` in this release. |

---

## `manifests/file_inventory.csv`

Audit inventory. One row per TR-6 file. Paths are relative to the TR-6 root.

| Field | Meaning |
| --- | --- |
| `path` | Relative path. |
| `size_bytes`, `mtime` | Size and local modification time at audit. |
| `extension` | Suffix or `[none]`. |
| `source` | `Normal`, `Classified`, or `root`. |
| `produce`, `label` | Directory produce and spoilage label (empty when absent). |
| `modality` | Apparent modality. |
| `read_status`, `validation_status` | Audit results. |
| `format`, `width`, `height`, `color_mode` | Image metadata; empty for non-images. |
| `timestamp_from_filename` | Parsed filename time. |
| `thermal_temperature_1_c`, `thermal_temperature_2_c` | Values parsed from thermal filenames; meaning unverified. |
| `sha256` | File hash. |
| `error` | Empty unless a read/parse error occurred. |

---

## `manifests/duplicate_groups.csv`

One row per exact SHA-256 group with two or more members.

| Field | Meaning |
| --- | --- |
| `duplicate_group_id` | Group id from the master manifest. |
| `content_id` | `tr6c_<sha256>`. |
| `sha256` | Shared file hash. |
| `size_bytes` | Byte size of each copy. |
| `member_count` | Number of exact copies. |
| `cross_source_duplicate` | Copies span Normal and Classified. |
| `cross_label_conflict` | Copies span both spoilage labels. |
| `produce_types` | Distinct produce directory names, semicolon-separated. |
| `observed_labels` | Distinct spoilage labels among members, semicolon-separated. |
| `source_directories` | Distinct trees among members. |
| `canonical_path` | Deterministic canonical relative path. |
| `member_paths` | All member relative paths, semicolon-separated. |

Duplicates are **not** deleted. Conflicting labels are **not** resolved.

---

## `manifests/duplicate_group_members.csv`

Long-form member list from the audit (`exact_duplicate_files.csv`).

| Field | Meaning |
| --- | --- |
| `duplicate_group` | Audit group id. |
| `sha256`, `size_bytes`, `member_count` | Shared identity. |
| `cross_source`, `cross_label`, `cross_modality` | Group flags. |
| `path` | One member relative path. |

---

## `manifests/label_conflict_report.csv`

The 170 unique hashes that appear under both `Spoiled` and `Not_spoiled`.

| Field | Meaning |
| --- | --- |
| `content_id` | Conflicting content. |
| `duplicate_group_id` | Matching duplicate group. |
| `reason_code` | `cross_label_exact_duplicate_conflict`. |
| `observed_labels` | `Not_spoiled;Spoiled`. |
| `affected_record_count` | Paths involved. |
| `affected_paths` | Semicolon-separated relative paths. |
| `decision` | `exclude_from_spoilage_supervision_and_pilot_pending_provenance`. No silent relabel. |
| `recorded_at` | UTC timestamp when the conflict was logged. |

---

## `manifests/modality_inventory.csv`

Counts rolled up from the master manifest.

| Field | Meaning |
| --- | --- |
| `source_directory` | `Normal`, `Classified`, or `root`. |
| `produce_type` | Produce folder or `unknown`. |
| `spoilage_label` | Inherited label or `unknown`. |
| `apparent_modality` | Apparent modality. |
| `file_count` | Rows in this stratum. |
| `unique_content_ids` | Distinct hashes. |
| `image_count` | Rows with JPEG image metadata. |
| `cross_label_conflict_files` | Rows with `cross_label_conflict=true`. |
| `size_bytes` | Sum of `size_bytes`. |

---

## `manifests/pilot_manifest.csv`

96 content-unique, conflict-free Normal images (8 per produce × modality). Seed `20261012`.

| Field | Meaning |
| --- | --- |
| `pilot_id` | Stable id `tr6p_###`. |
| `record_id`, `content_id`, `sha256` | Links to the master manifest. |
| `original_relative_path` | TR-6 relative path. |
| `source_path_relative_to_workspace` | Layout hint only. |
| `produce_type`, `apparent_modality` | Sampling stratum. |
| `spoilage_label` | Always `unknown` for this pilot. |
| `spoilage_label_status` | `not_used_for_pilot`. |
| `cross_label_conflict` | Always `false` by construction. |
| `filename_timestamp`, `width`, `height` | Inherited metadata. |
| `selection_seed` | `20261012`. |
| `selection_method` | Deterministic canonical Normal sampling. |
| `annotation_status` | Copied at build time; see `annotation_status.csv` for the live ledger. |
| `fruit_mask_required` | `true` for annotatable images. |
| `visible_defect_mask` | `conditional_if_visually_identifiable`. |

---

## `manifests/calibration_batch.csv`

The first image of each produce × modality stratum (12 rows). Same columns as the pilot manifest. These 12 images were imported for Label Studio calibration. Human annotations are **not** complete.

---

## `manifests/annotation_status.csv`

Compact live ledger for all 96 pilot images. Distinguishes pending work from completed human annotation.

| Field | Meaning |
| --- | --- |
| `pilot_id`, `content_id` | Image identity. |
| `annotation_status` | `pending` (84 images) or `pending_review` (12 calibration images). Allowed values also include `annotated`, `reviewed`, `excluded`; none of those are used yet. |
| `proposal_status` | `none` or `proposal_only`. |
| `label_studio_status` | `not_imported` (84) or `unsubmitted` (12). No `submitted` rows. |
| `human_annotation_file` | Empty: no human export exists. |
| `proposal_coco_path` | `annotations/coco_annotations.json` when a proposal exists. |
| `proposal_raster_path` | Local-only PNG path. The PNG is **not** in this package. |
| `fruit_instance_count`, `visible_defect_instance_count` | Empty until a human annotation exists. |
| `image_quality` | Empty in the ledger; proposal quality is in `proposal_index.csv`. |
| `label_studio_project_id`, `label_studio_task_id` | Local Label Studio ids for the 12 calibration tasks. |
| `known_issue` | From `proposal_index.csv` when present. |
| `notes` | Ledger notes. |

**Completed human annotations: 0.**

---

## `annotations/annotation_records.csv`

Full workflow ledger (same 96 rows). Additional fields:

| Field | Meaning |
| --- | --- |
| `annotator_id`, `reviewer_id` | Empty until a human acts. |
| `annotation_file`, `raster_mask_path` | Human output paths; empty. |
| `exclusion_reason` | Empty unless `excluded`. |
| `annotation_started_at`, `annotation_completed_at`, `reviewed_at` | Empty. |
| `proposal_generator_id` | `cursor-agent-calibration-assist` for the 12 proposals. |
| `proposal_generated_at` | UTC time the proposal COCO/masks were written. |
| `proposal_suggested_quality` | `annotatable` or `ambiguous` from the proposal script. |

---

## `annotations/proposal_index.csv`

Index of the 12 Python-assisted proposals.

| Field | Meaning |
| --- | --- |
| `pilot_id`, `label_studio_task_id` | Identity. |
| `proposal_status` | Always `proposal_only`. |
| `proposal_raster_path` | Excluded PNG path. |
| `proposal_coco_path` | `annotations/coco_annotations.json`. |
| `proposal_suggested_quality` | `annotatable` or `ambiguous`. |
| `known_issue` | Human-readable caveat. `tr6p_073` is a known incorrect thermal proposal (table, not fruit). |

---

## `annotations/coco_annotations.json`

COCO-style JSON with 96 image records and 12 category-1 (`fruit_visible_region`) polygons. These polygons are **Python proposals**, not ground truth. Coordinates are stored JPEG pixels without EXIF transpose. Category 2 (`visible_defect_region`) has no proposal instances.

---

## Methane audit tables

`manifests/methane_files.csv` — one row per methane text file: encoding, delimiter, column names, record counts, and min/median/max of parsed ADC / Rs / Rs/R0 / ppm. These are **audit summaries**, not a new sensor campaign.

`manifests/methane_issues.csv` — parse issues (`null_marker`, malformed lines) with source-relative `path` and `line`.

`manifests/methane_normal_classified_correspondence.csv` — whether each Classified methane file is an exact text span of the matching Normal file.

Raw `.txt` methane files are not included.

---

## Other audit tables

`manifests/image_summary.csv` — per-stratum JPEG counts and size percentiles.

`manifests/classified_normal_exact_duplicates.csv` — how many Classified files are exact Normal duplicates, by stratum.

`manifests/image_correspondence_summary.csv` — timestamp-based RGB/thermal candidate counts. `verified_cross_modal_pairs` is 0 everywhere.

`manifests/inferred_image_sessions.csv` — **timestamp clusters**, not specimen IDs. `derivation` states the heuristic.

`manifests/probable_session_correspondence.csv` — mutual-nearest timestamp session candidates. Status is `probable_session_candidate`, not verified pairing.

`manifests/directory_summary.csv`, `manifests/extension_summary.csv`, `manifests/produce_modality_summary.csv` — inventory rollups.

`manifests/errors.csv` — audit errors (header only; none recorded).

---

## Reports

`reports/validation_report.json` and `.md` — schema/integrity result `pass` with 0 human-complete annotations and 12 proposal polygons.

`reports/audit_summary.json`, `reports/audit_report.md` — sanitised audit totals.

`reports/build_summary.json` — sanitised Phase 1 build totals.

`reports/file_count_summary.json` — counts of files **inside this package**.

`reports/package_validation.json` — packaging checks (no absolute paths, no source binaries, no secrets).

`reports/licence_evidence.json` — Figshare API licence block as retrieved.

`reports/calibration_task_status.md` — 12 calibration tasks, all unsubmitted.

`reports/calibration_annotation_summary.json` — proposal polygon statistics. Overlay/PNG paths listed there are **not** packaged.
