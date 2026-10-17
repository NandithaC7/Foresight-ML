# Licence and attribution

Package: Foresight-TR6-plus-dataset-v1.0.0  
This file records **verified evidence**, not an assumption.

## 1. Source dataset (TR-6 / TriModal Ripeness 6)

**Canonical publication (not this package):**

- Title: TriModal Ripeness 6
- Local folder name: `TR-6`
- Authors: T Bagyammal; Yogini Aishwaryaa P T S; Krishna Deepak; Devika Unnikrishnan (2025)
- Figshare record: https://figshare.com/articles/dataset/TriModal_Ripeness_6/30783827
- DOI: https://doi.org/10.6084/m9.figshare.30783827.v1
- Figshare article id: `30783827`
- Figshare file: `TR-6.zip` (id `60094544`, size `20388430589` bytes, MD5 `cdbcc4a667051aa35d46c2de71a723d9`)

**Licence evidence retrieved 2026-10-15 from the public Figshare API**  
`GET https://api.figshare.com/v2/articles/30783827`:

```json
"license": {
  "value": 1,
  "name": "CC BY 4.0",
  "url": "https://creativecommons.org/licenses/by/4.0/"
}
```

The local `TR-6/README.txt` describes modalities and folder layout. It does **not** contain a licence statement.

**What CC BY 4.0 permits (source terms, not a legal opinion):** reuse, redistribution and adaptation of the licensed material with attribution, licence notice, and indication of changes. It does not waive moral rights or require us to re-host the 20 GB archive.

**What this v1.0.0 package does with that evidence:**

- Attributes TR-6 to the Figshare authors and DOI above.
- Does **not** include original TR-6 images, methane `.txt` files, or pixel derivatives (contact sheets, overlays, raster masks).
- Those binaries remain at the canonical Figshare record. Users must obtain TR-6 from that DOI.
- Re-hosting the original 20 GB archive on IEEE DataPort is **not** part of this release, even though CC BY 4.0 would allow redistribution with attribution. This package is a derived metadata resource, not a second copy of TR-6.

If IEEE DataPort later requires the image archive, obtain it from Figshare and keep TR-6 authorship and CC BY 4.0 notices intact. Do not present TR-6 pixels as newly collected Foresight data.

## 2. This derived resource (Foresight-TR6+)

Foresight-TR6+ is **not** a newly collected fruit dataset. It is a provenance-aware derived resource: manifests, duplicate and conflict reports, audit and validation scripts, an annotation protocol, and documentation produced from a read-only audit of a local TR-6 copy.

**Licence of our original contributions** (documentation, scripts, and derived tables that we authored):

Creative Commons Attribution 4.0 International (CC BY 4.0)  
https://creativecommons.org/licenses/by/4.0/

Please cite both this package (once an IEEE DataPort DOI exists) and the original TR-6 Figshare DOI.

## 3. What is blocked from this upload

The following must **not** be uploaded with v1.0.0:

- Original TR-6 JPEG images or methane text files
- Modified or noisy copies of those images
- Review contact sheets, calibration overlays, or proposal raster masks derived from source pixels
- Label Studio databases, virtualenv, secrets, or local absolute paths

Python proposal polygons in `annotations/coco_annotations.json` are coordinate metadata marked `proposal_only`. They are **not** completed human ground truth and are **not** independently verified.

## 4. Required citation of the source

Bagyammal, T; P T S, Yogini Aishwaryaa; Deepak, Krishna; Unnikrishnan, Devika (2025). TriModal Ripeness 6. figshare. Dataset. https://doi.org/10.6084/m9.figshare.30783827.v1
