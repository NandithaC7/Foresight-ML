# Foresight-TR6+ dataset v1.0.0

Derived dataset/resource for provenance-aware use of **TriModal Ripeness 6 (TR-6)**.

This is **not** a newly collected image dataset. Original sRGB images, thermal IR-fusion images, and methane files were collected by the TR-6 authors and remain at their Figshare record. This package publishes **our** manifests, audit findings, validation scripts, annotation protocol, and documentation.

## Scope

Included:

- Master provenance manifest for every audited TR-6 file (relative path + SHA-256)
- File inventory, modality inventory, duplicate-group inventory, and label-conflict report
- 96-image pilot selection (conflict-free, canonical Normal content, seed `20261012`)
- Annotation protocol and annotation-status ledger
- Reproducible audit, validation, and packaging scripts
- Actual validation results from the local audit (paths sanitised)

Not included:

- Original TR-6 images or methane text
- Noisy or otherwise modified copies of those images
- Completed human-reviewed segmentation ground truth (none exists yet)
- Trained models, experimental metrics, specimen IDs, or cross-modal pairs

## Provenance

| Item | Record |
| --- | --- |
| Source dataset | TriModal Ripeness 6 (local name TR-6) |
| Source DOI | https://doi.org/10.6084/m9.figshare.30783827.v1 |
| Source licence (Figshare API) | CC BY 4.0 |
| Source authors | Bagyammal, T; P T S, Yogini Aishwaryaa; Deepak, Krishna; Unnikrishnan, Devika (2025) |
| This resource | Foresight-TR6+ derived manifests and documentation |
| This version | 1.0.0 |

See `LICENSE_AND_ATTRIBUTION.md`.

## Key audit findings (from the local read-only audit)

- 21,653 files; 21,626 valid JPEGs; 18 methane files; 0 corrupt images
- 10,776 unique image hashes; 10,589 exact-duplicate groups
- All 10,796 Classified images are exact byte duplicates of Normal images
- 170 unique image hashes appear under both `Spoiled` and `Not_spoiled`
- 0 verified specimen-level RGB–thermal–methane links
- Inherited spoilage labels are **not** independently verified

Do not treat Classified and Normal as independent datasets. Do not silently drop duplicates or pick a winner on conflicting labels.

## Package structure

```
README.md
DATA_DICTIONARY.md
LICENSE_AND_ATTRIBUTION.md
CITATION.md
VERSION
manifests/
scripts/
reports/
annotations/
docs/
config/
future/noise-augmentation/
imports/
```

## Usage

1. Download TR-6 from the Figshare DOI above. Do not expect images inside this ZIP.
2. Place it so that `TR-6/` is a sibling of a Foresight-TR6+ workspace, or pass `--dataset` explicitly.
3. Read `docs/annotation_protocol.md` before any labelling.
4. Treat `spoilage_label` as inherited and unverified.
5. Use `duplicate_group_id` and `content_id` to avoid leakage; split on content or specimen, never on individual duplicate copies.

## Reproduction commands

From a workspace that contains this package plus a local TR-6 tree:

```bash
# Read-only source audit (writes outside TR-6)
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_tr6.py \
  --dataset /path/to/TR-6 \
  --output /path/to/audit-output

# Rebuild manifests from audit outputs (does not copy images)
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_extension.py \
  --dataset /path/to/TR-6 \
  --audit-output /path/to/audit-output \
  --workspace /path/to/Foresight-TR6-plus \
  --seed 20261012 \
  --per-produce-modality 8

# Integrity and schema checks
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_extension.py \
  --dataset /path/to/TR-6 \
  --workspace /path/to/Foresight-TR6-plus \
  --hash-mode pilot
```

Rebuild the publication ZIP (excludes source images):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package_release.py \
  --workspace /path/to/Foresight-TR6-plus \
  --audit-output /path/to/audit-output \
  --version 1.0.0
```

## Limitations

- No human-reviewed fruit or defect masks are published as ground truth.
- Twelve computer-assisted proposal polygons exist and are labelled `proposal_only`.
- No official train/validation/test split is published, because specimen IDs are unknown.
- Methane and thermal filenames are not mapped to verified physical specimens.
- A noise-augmentation pipeline is documented under `future/` and is **not** part of the v1.0.0 data files.

## IEEE DataPort

This ZIP is prepared for manual upload. It has **not** been uploaded and has **no** IEEE DataPort DOI until you submit it.
