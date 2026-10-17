# Manual Label Studio guide — 12-image calibration

Human annotations are created only in Label Studio. Python masks are unverified proposals.

## Open the project

1. Confirm Label Studio is running locally.
2. Open [http://localhost:8080/projects/1/data/](http://localhost:8080/projects/1/data/).
3. Sign in with the local Label Studio account (this is not Google login):
   - Email: the address already accepted by this local instance
   - Password: `foresight-calibration-local`
4. You should see project **Foresight TR6+ Calibration**, **Tasks: 12 / 12**, **Submitted annotations: 0**.
5. Click **Label All Tasks**, or open a row and click **Label**.

Do not click **Sign up**. That creates a new empty organization. Do not **Import** `annotations/coco_annotations.json` or the PNG proposals as accepted annotations.

Task URLs:

- Data manager: [http://localhost:8080/projects/1/data/](http://localhost:8080/projects/1/data/)
- Labeling queue: [http://localhost:8080/projects/1/data/?tab=1&labeling=1](http://localhost:8080/projects/1/data/?tab=1&labeling=1)

## Images you will see

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

sRGB files are stored 4000×3000 with EXIF orientation 6. Label Studio may display them upright. Do not rotate the source files. Prefer drawing on the displayed fruit without using the rotate control unless you cannot see the specimen.

## Draw the fruit polygon

1. Select **fruit_visible_region**.
2. Click around the visible produce: skin, attached stem/calyx, and any damaged tissue that is still part of the specimen.
3. Close the polygon. Adjust vertices so the outline follows the fruit, not the table.
4. Exclude background, table, wall, cast shadows, reflections, and thermal halo.
5. On thermal images, place the boundary at the strongest stable fruit-to-background transition. If two cutoffs look equally plausible, mark the image **ambiguous** and explain the cutoff in Notes.

## Visible defects

Draw **visible_defect_region** only when a localized physical boundary is visible in this image: mold-like growth, clearly bounded bruise/rot/lesion/cut, or collapsed/necrotic tissue.

Do **not** draw a defect for:

- Ripening color, lenticels, stem scars, expected texture
- Banana brown spots that look like ordinary ripening
- Pale carrot skin variation
- Guava speckling
- Tomato calyx / stem scar (include that in the fruit mask)
- Thermal color, palette noise, hot/cold blobs, or halo
- Anything inferred only from a `Spoiled` folder name

An image may have a fruit mask and zero defect masks. That means “no confidently delineable visible defect,” not “not spoiled.”

## Image-level decision (required)

Choose exactly one:

- **annotatable**: fruit outline is repeatable; save the fruit polygon.
- **ambiguous**: fruit is present but the edge, halo, crop, or possible defect is uncertain. Still draw a fruit polygon if a repeatable boundary exists, and write the reason.
- **exclude**: produce is absent, undecodable, wrong image, or too degraded to defend a fruit mask. Write the exclusion reason. Do not exclude merely because there is no defect.

## Known bad proposal — do not copy

**tr6p_073** (LS task 10, mango thermal) has a Python proposal that covers table/background, not the mango. Ignore `annotations/masks/tr6p_073.png` and the matching overlay. Draw the fruit from the original thermal image.

Other thermal proposals (banana, guava, gooseberry, tomato) are also unverified and often too tight, too loose, or haloed. Use them only as optional visual comparison in `reports/calibration-overlays/`, never as the saved Label Studio polygon.

## Save and confirm

1. After the polygon(s), disposition, and notes are set, click **Submit** (not just Skip).
2. Return to [http://localhost:8080/projects/1/data/](http://localhost:8080/projects/1/data/).
3. Confirm **Submitted annotations** increased and that the task row shows a completed annotation (Completed / Annotated by populated).
4. Re-open the task. The fruit polygon and disposition must still be there.
5. If you only pressed Skip, or the browser lost the session, the task is not saved.

A saved human annotation exists only in Label Studio until a later export writes `annotations/human_coco_annotations.json`. The file `annotations/coco_annotations.json` remains a Python proposal archive and must not be treated as the completed export.

## After all 12 are submitted

Tell the assistant to read Label Studio submissions and export human COCO only. Do not ask it to copy the proposal file over the human export.
