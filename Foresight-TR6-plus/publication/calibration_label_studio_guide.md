# Manual Label Studio guide — 12-image calibration

Human annotations are created only in Label Studio. Python masks are unverified proposals. Local login credentials are **not** published in this package.

## Open the project

1. Confirm Label Studio is running locally against your own TR-6 copy.
2. Open the local calibration project data manager.
3. Sign in with the account you created on that instance. Do not publish that password.
4. You should see 12 tasks and 0 submitted annotations at the time of this release.
5. Label the 12 calibration images only. Do not import `annotations/coco_annotations.json` or PNG proposals as accepted ground truth.

## Images in the calibration batch

| LS task | `pilot_id` | Produce | Modality | Original path in TR-6 |
|---|---|---|---|---|
| 1 | tr6p_001 | Banana | sRGB | `Normal/Banana/sRGB_images/20250911_101508.jpg` |
| 2 | tr6p_009 | Banana | thermal | `Normal/Banana/IR_fusion_images/20250915_093303_29.1C_30.5C.jpg` |
| 3 | tr6p_017 | Carrot | sRGB | `Normal/Carrot/sRGB_images/20250725_171408.jpg` |
| 4 | tr6p_025 | Carrot | thermal | `Normal/Carrot/IR_fusion_images/20250725_170448_25.4C_28.3C.jpg` |
| 5 | tr6p_033 | Guava | sRGB | `Normal/Guava/sRGB_images/20250625_135610.jpg` |
| 6 | tr6p_041 | Guava | thermal | `Normal/Guava/IR_fusion_images/20250625_085941_27.5C_29.0C.jpg` |
| 7 | tr6p_049 | Indian gooseberry | sRGB | `Normal/Indian_Gooseberry/sRGB_images/20250725_171131.jpg` |
| 8 | tr6p_057 | Indian gooseberry | thermal | `Normal/Indian_Gooseberry/IR_fusion_images/20250729_132753_29.5C_31.3C.jpg` |
| 9 | tr6p_065 | Mango | sRGB | `Normal/Mango/sRGB_images/20250920_123146.jpg` |
| 10 | **tr6p_073** | Mango | thermal | `Normal/Mango/IR_fusion_images/20250920_162228_31.2C_32.8C.jpg` |
| 11 | tr6p_081 | Tomato | sRGB | `Normal/Tomato/sRGB_images/20250726_165434.jpg` |
| 12 | tr6p_089 | Tomato | thermal | `Normal/Tomato/IR_fusion_images/20250725_083842_27.3C_28.3C.jpg` |

`tr6p_073` has a known bad Python proposal (table, not fruit). Draw the fruit yourself.

sRGB files are stored 4000×3000 with EXIF orientation 6. Do not rotate the source files.

## Draw the fruit polygon

1. Select `fruit_visible_region`.
2. Outline visible produce: skin, attached stem/calyx, and damaged tissue that is still part of the specimen.
3. Exclude background, table, wall, cast shadows, reflections, and thermal halo.
4. On thermal images, place the boundary at the strongest stable fruit-to-background transition. If two cutoffs look equally plausible, mark the image `ambiguous`.

## Visible defects

Draw `visible_defect_region` only when a localized physical boundary is visually defensible. Ripening colour, texture, and thermal palette variation are not defects by themselves.

## After labelling

Export human submissions to `annotations/human_coco_annotations.json`. Never copy proposal polygons into that file. Update `annotation_status` to `annotated` only after a real submission exists.
