# Data Dictionary

## Master manifest

`manifests/master_manifest.csv` contains one row for every audited TR-6 file.

- `record_id`: Stable identifier derived from the original relative path.
- `content_id`: Stable identifier containing the file SHA-256. Equal values mean exact byte identity.
- `source_dataset`: Always `TR-6`.
- `original_relative_path`: Path relative to the TR-6 root.
- `source_path_relative_to_workspace`: Relative reference from this workspace; no source file is copied.
- `sha256`, `size_bytes`, `extension`: Audited file identity and storage metadata.
- `source_directory`: `Normal`, `Classified` or `root`.
- `produce_type`: One of six documented produce types, or `unknown`.
- `apparent_modality`: Directory/README-derived modality; not a semantic pixel classifier.
- `existing_path_label`: Literal inherited directory label or `unknown`.
- `spoilage_label`: Inherited Classified-tree label or `unknown`. Normal remains unknown.
- `label_origin`: `inherited_from_directory_name` or `unavailable`.
- `label_independently_verified`: Always false in Phase 1.
- `label_status`: `unlabeled`, `inherited_unverified` or `inherited_conflicting`.
- `filename_timestamp`: Parsed filename timestamp or `unknown`.
- `timestamp_status`: Records that filename time is unverified and timezone-naive.
- `width`, `height`, `image_format`, `color_mode`: Audited image metadata or `unknown`.
- `file_read_status`, `file_validation_status`: Results inherited from the read-only audit.
- `duplicate_group_id`: Exact SHA-256 duplicate group or `none`.
- `duplicate_member_count`: Number of exact copies in that group.
- `cross_source_duplicate`: Exact content occurs across source trees.
- `cross_label_conflict`: Exact content occurs under both spoilage labels.
- `canonical_content_reference`: One deterministic path selected for content-level operations. This does not select a correct label.
- `specimen_id`, `capture_id`, `view_id`, `cross_modal_group_id`: `unknown`; never inferred.
- `segmentation_pilot_eligible`: Valid, canonical, conflict-free Normal image eligible for deterministic sampling.
- `spoilage_supervision_eligible`: False in this phase.

## Pilot manifest

`manifests/pilot_manifest.csv` contains 96 content-unique, conflict-free image references.

- `pilot_id`: Stable pilot ordering identifier.
- `record_id`, `content_id`, `sha256`: Links to the master manifest.
- `spoilage_label`: Always `unknown`.
- `selection_seed`, `selection_method`: Reproducibility metadata.
- `annotation_status`: Initially `pending`.
- `fruit_mask_required`: True for annotatable images.
- `visible_defect_mask`: Conditional on a defensible visible region.

## Annotation records

`annotations/annotation_records.csv` tracks workflow state and exported annotation paths.

Allowed `annotation_status` values:

- `pending`: no human annotation started.
- `pending_review`: human Label Studio annotation is incomplete; a Python proposal may exist.
- `annotated`: a human submitted the image in Label Studio.
- `reviewed`: a human review pass accepted the annotation.
- `excluded`: rejected with `exclusion_reason`.

Separate proposal and Label Studio fields:

- `proposal_status`: `none` or `proposal_only`.
- `proposal_coco_path`, `proposal_raster_path`: comparison-only files. Not ground truth.
- `label_studio_status`: `not_imported`, `unsubmitted`, `submitted`, or `cancelled`.
- `human_annotation_file`: path to a human export. Must not be `annotations/coco_annotations.json`.

Empty human annotation fields mean that no human annotation has been created; they are not missing ground truth.
