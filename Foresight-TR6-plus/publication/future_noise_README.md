# Future: controlled noise augmentation

This folder is **not** part of the v1.0.0 data files. No noisy images were generated for publication.

`generate_noise_dataset.py` and `noise_generation.json` define a later experiment:

- Sources: conflict-free canonical Normal images from the pilot (or a 24-image subset).
- Transforms (stored JPEG pixels, no EXIF transpose): Gaussian, salt-and-pepper, mild speckle.
- Split assignment is by `content_id` (70/15/15). Derivatives inherit the source split and must not be treated as independent specimens.
- Inherited spoilage labels remain unverified.
- Original TR-6 files are never overwritten.

Do not run a full-dataset job from this package. After publication, if redistribution of pixel derivatives is confirmed under CC BY 4.0 with attribution, generate a **separate** versioned package, validate it, and document it independently of v1.0.0.

Estimate-only:

```bash
python3 generate_noise_dataset.py --estimate-only --source-set pilot_sample
```
