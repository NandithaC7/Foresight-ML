# Pilot Visual Feasibility Review

Review basis: two selected images per produce × modality stratum (24 images total) shown in the local contact sheets. This is a feasibility review, not annotation or ground truth.

## sRGB observations

- The target produce is centered and visually separable from the light background in all 12 reviewed examples.
- Fruit-visible-region masks appear feasible.
- Stems and calyxes require the explicit inclusion convention in the protocol.
- Several fruits show spots, discoloration or surface texture, but the review cannot determine whether these are defects, normal appearance or spoilage.
- Visible-defect polygons must therefore remain conditional and require human judgment at native resolution.
- Cast shadows are present and must be excluded from fruit masks.

## Thermal IR-fusion observations

- Banana, carrot, mango and tomato silhouettes are generally distinct in the reviewed samples.
- Guava and Indian Gooseberry examples have lower fruit/background contrast and diffuse boundaries.
- Thermal fruit-visible-region masks appear feasible for many images, with ambiguity flags likely needed for low-contrast cases.
- Local thermal color variation is not sufficient evidence of a visible physical defect. No thermal defect annotation should be forced from these review sheets.

## Pilot recommendation

Proceed first with a 12-image calibration batch: one sRGB and one thermal image for each produce type. Review and adjudicate those masks before annotating the remaining 84 images.

Do not scale beyond 96 images until:

1. Fruit boundary conventions are consistent across modalities.
2. The reviewer agrees on stem/calyx handling.
3. Defect-versus-normal-texture criteria are workable on native-resolution sRGB.
4. Thermal ambiguity and exclusion rates are measured.
5. The annotation export passes validation.
