# Walkthrough: Stylized Multi-Region Illustration (`Smoke_Stylized_Lantern`)

This example illustrates the full **Stage A -> Stage F** workflow executed against a disposable `640×480` document in live Krita `6.0.4` (`krita-mcp v1.7.0`), independent of character illustrations or fixed resolutions.

---

## Stage A — Visual Decomposition

Input lineart preview: [sample_lineart_fixture.png](./sample_lineart_fixture.png)

Visual inspection identifies:
- **Regions & Semantic Layers**:
  - `Lantern_Body_Base` (`#4A5264`): Upper dome cap (`198..442 × 126..188`) and trapezoid pedestal foot (`186..454 × 376..422`).
  - `Brass_Trim_Base` (`#D89B3C`, accents `#F2C96B`): Handle arch (`260..380 × 64..126`), riveted collar belt (`196..444 × 342..376`), and circular rivets (`(222, 359)`, `(418, 359)`).
  - `Glass_Panel_Base` (`#82D4E6`): Left, center, and right glass panels (`212..428 × 188..342`) divided by interior struts.
  - `Jewel_Inset_Base` (`#C93B5B` outer bezel, `#E85D78` inner facet): Center diamond emblem (`284..356 × 224..304`) with a soft semi-transparent (`alpha=68`) inner bevel line.
- **Intentional Negative Spaces (`DO_NOT_FILL`)**:
  - Exterior background `(10, 10)`, `(630, 10)`.
  - Enclosed handle loop cutout centered at `(320, 105)`.

---

## Stage B — Boundary Preparation & Leak Diagnosis

1. Locked `Original_Lineart` (`locked: true`), duplicated it, unlocked the duplicate, baked it to `Lineart_Fill_Reference`, deleted the duplicate group, and nested `Lineart_Fill_Reference` inside hidden `Fill_Assist_Hidden` (`visible: false`).
2. Exported `Fill_Assist_Hidden/Lineart_Fill_Reference` via `export_layers(trim=false)` (`mutated: false`).
3. Ran `scripts/lineart_fill_diagnostics.py`:
   - Detected a `3 px` contour break on the dome cap (`(320, 155) -> (10, 10)`, `narrowest_span: 3` at `(396, 125)`, suggested bridge `[395, 125] -> [399, 125]`).
   - Detected a `2 px` internal seam break between the glass panel and collar belt (`(275, 260) -> (320, 358)`, `narrowest_span: 2` at `(320, 340)`, suggested bridge `[318, 340] -> [321, 340]`).
   - Confirmed intentional handle aperture `(320, 105)` remained separated from surrounding trim (`status: "separated"`).

---

## Stage C — Fill Tool Execution & Failure Recovery

1. **Deliberate failure recovery test**: Running `select_content` on broken `(320, 155)` returned `selection: [0, 0, 640, 480]` (background flood). Immediately ran `undo(count=1)`.
2. **Helper repair**: Sealed the two verified breaks on hidden `Fill_Assist_Hidden/Lineart_Fill_Reference` (`[394, 126] -> [401, 126]` and `[317, 342] -> [323, 342]`, `stroke_width: 3`). Re-exported and confirmed `status: "separated"`.
3. **Fill Tool pass**: Filled `Lantern_Body_Base`, `Glass_Panel_Base`, and `Brass_Trim_Base` using `select_content(mode="contiguous", threshold=1, tolerance=3)` + `set_selection(mode="grow", amount=1)` + tight `draw(fill_rect)`.
4. **Polygonal fallback**: Because the diamond emblem's inner bevel ring was translucent (`alpha=68`), filled `Jewel_Inset_Base` cleanly using `select_polygon` bounded behind the outer ink diamond (zoom check: [sample_jewel_zoom_2x.png](./sample_jewel_zoom_2x.png)), then cleared the interior diamond core from `Glass_Panel_Base` beneath it so sibling material alphas stay disjoint.

---

## Stage D, E & F — Organisation, Audit & Result

Final composite output (flat base colours only, no shading/rendering): [sample_base_coloured_preview.png](./sample_base_coloured_preview.png)

Stage E `base_colour_audit.py` on the background-hidden transparent cutout confirmed:
- `0` contaminated points (`(10, 10)`, `(630, 10)`, `(320, 105)` all `rgba=(0, 0, 0, 0)`).
- `0` exterior non-zero alpha pixels outside subject bounds `[184, 62, 456, 424]`.
- `0` pairwise solid-alpha (`alpha >= 200`) overlaps across sibling `Base_Colours` layers.
- `1` residual `4 px` (`2×2`) unfilled point surfaced at `(319, 341)` right beneath the `3 px` un-inked gap in `Original_Lineart` (`Original_Lineart` intentionally left unedited).

*The same workflow scales directly to multi-part character illustrations (such as the `1024×1536` Gojo V2 regression benchmark in [validation_report.md](../reports/validation_report.md)): semantic material layers under `Base_Colours`, minimal seals strictly on `Fill_Assist_Hidden/Lineart_Fill_Reference`, contiguous fills with `grow=1`, polygon fallback on complex soft eyes, and background-hidden isolation verification.*
