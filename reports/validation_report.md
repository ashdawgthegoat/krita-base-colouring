# Validation Report: `krita-base-colouring`

- **Package**: `krita-base-colouring` (standalone, character-agnostic, canvas-independent)
- **Test environment**: Python `3.13.5` (standard library only), Krita `6.0.4 (git 57db7cd)`, `krita-mcp v1.7.0`, Antigravity CLI `agy 1.5.10`

---

## 1. Offline Automated Tests (Synthetic Fixtures)

Command run from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

- **Result**: `Ran 9 tests in 0.052s` — **OK (`9/9` passed, `0` skipped, `0` failed)**.
- Covered synthetic fixtures (`tests/fixtures/generate_fixtures.py`):
  - `test_seed_validation_catches_opaque_ink_and_oob`: rejects opaque ink pixel (`alpha=255`) and out-of-bounds seed before issuing Krita calls.
  - `test_broken_contour_detects_background_and_neighbor_bottlenecks`: pinpoints both a `3 px` top contour break (`(64..66, 15..16)`) and a `2 px` internal seam break (`(89..90, 58..59)`) via shortest-path bottleneck width scanning.
  - `test_sealed_contour_separates_regions_and_discovers_negative_space_and_jewel`: verifies `status == "separated"`, finds all `4` enclosed interior pockets, and identifies the intentional cutout aperture `(30, 37, 17, 46)`.
  - `test_clean_cutout_passes_and_preserves_negative_space`: validates background/negative-space transparency (`(5, 5)`, `(38, 60)` -> `alpha == 0`) and confirms `find_unfilled_enclosed_islands(..., transparent_img=...)` does not misreport filled `#FFFFFF` base regions as unfilled holes.
  - `test_detects_leaked_background_and_unfilled_hole`: detects contaminated background corner and an isolated `36 px` (`6×6`) unfilled hole inside a composite test image.
  - `test_audit_layer_disjointness_detects_sibling_contamination`: catches `25 px` overlapping solid-alpha contamination between sibling layers.
  - `test_union_bboxes_clamps_to_arbitrary_canvas`, `test_contiguous_fill_batches_chunk_within_limit`, `test_seal_polygon_and_recovery_batches`: verify `<= 64`-edit batch chunking, clamped dynamic bounding boxes, seal draw commands, polygon fill batches, and `clear`-then-refill recovery batches.

---

## 2. Live Krita MCP Disposable-Document Smoke Test (`Smoke_Stylized_Lantern`)

Executed in live Krita `6.0.4` on a newly created `640×480` document (`300 DPI`, `RGBA/U8`), completely independent of existing Gojo documents:

1. **Stage A & B**: Locked `Original_Lineart` (`locked: true`), duplicated it, unlocked duplicate (`required by bake_layer`), baked to `Lineart_Fill_Reference`, deleted the intermediate duplicate, and nested `Lineart_Fill_Reference` under `Fill_Assist_Hidden` (`visible: false`). Exported `Lineart_Fill_Reference.png` via `export_layers(trim=false)` (`mutated: false`).
   - `lineart_fill_diagnostics.py` located a deliberate `3 px` dome-cap contour break at `(396, 125)` (`status: "leaked"`, `bridge: 395,125 -> 399,125`) and a `2 px` seam break at `(320, 340)` (`status: "leaked"`, `bridge: 318,340 -> 321,340`), while confirming the handle negative-space loop `(320, 105)` remained separated.
2. **Stage C Failure Recovery & Repair**:
   - Deliberately attempted `select_content` on broken seed `(320, 155)`, observed overflow bbox `[0, 0, 640, 480]`, immediately rolled back via `undo(count=1)`, and repaired only the two diagnosed breaks on `Fill_Assist_Hidden/Lineart_Fill_Reference`.
   - Re-exported `Lineart_Fill_Reference` and confirmed `status: "separated"` across all 12 fillable components.
   - Filled `Lantern_Body_Base`, `Glass_Panel_Base`, and `Brass_Trim_Base` via `select_content(contiguous, threshold=1, tolerance=3)` + `set_selection(grow=1)` + tight `draw(fill_rect)`.
   - Used `select_polygon` fallback on `Jewel_Inset_Base` where a translucent inner bevel ring (`#12141a44`) split the jewel softly, then cleared the interior diamond core from `Glass_Panel_Base` beneath it.
3. **Stage D, E & F Verification**:
   - Saved the disposable layered `.kra` output (`modified: false`) and exported [examples/sample_base_coloured_preview.png](../examples/sample_base_coloured_preview.png).
   - Exported background-hidden cutout and individual `Base_Colours` layers (`export_layers(trim=false)`).
   - `base_colour_audit.py` reported:
     - `contaminated_empty_points: 0` (`(10, 10)`, `(630, 10)`, `(320, 105)` all `rgba=(0, 0, 0, 0)`)
     - `exterior_nonzero_alpha_pixels: 0` outside `[184, 62, 456, 424]`
     - `subject_opaque_pixels: 72009`
     - `audit_layer_disjointness(alpha_threshold=200)`: `[]` (`0` sibling core overlaps)
     - Residual unfilled pixels inside contours: `1` item (`(319, 341)`, `4 px` / `2×2` bbox `[319, 341, 2, 2]`) directly corresponding to the un-inked gap between `Original_Lineart` strokes where `Fill_Assist_Hidden` bridged `y=342` (original `Original_Lineart` intentionally kept unedited).
   - Closed the disposable smoke document (`close_document`), leaving existing source and reference `.kra` documents untouched.

---

## 3. Gojo V2 Read-Only Regression Benchmark

Evaluated `scripts/lineart_fill_diagnostics.py` and `scripts/base_colour_audit.py` read-only against Gojo V2 session exports (`1024×1536`, zero hardcoded Gojo values inside the skill package):
- `check_seeds` cleanly flagged opaque ink `(532, 630)` (`alpha=140`, `opaque_ink_pixel`) while accepting interior seeds `(510, 35)`, `(522, 146)`, `(560, 620)`.
- `audit_transparent_cutout` on `v2_base_transparent.png` verified `passed: true`, `contaminated_empty_points: 0` (`(10, 10)`, `(1010, 10)`, arm-torso gap `(367, 412)`, between-legs gap `(457, 1196)`), `exterior_nonzero_alpha_pixels: 0` outside `[126, 7, 865, 1525]`, and `subject_opaque_pixels: 452078`.
- `find_unfilled_enclosed_islands(..., transparent_img=v2_base_transparent)` surfaced `13` tiny transparent pockets `>= 6 px` (ground-shadow hatch negative spaces, `23 px` intentional left armpit sleeve opening `(352, 436)`, and minor `13–14 px` edge crevices).

---

## 4. Antigravity Skill Discovery Check

- Linked `.agents/skills/krita-base-colouring -> ../../skills/krita-base-colouring` inside the workspace root (per `agy-customizations` docs).
- Verified `SKILL.md` reads cleanly through the symlink.
- Invoked `agy --mode=plan --print='...'` from the workspace root and observed `krita-base-colouring` automatically discovered and listed under Available skills pointing to `.agents/skills/krita-base-colouring/SKILL.md`.

---

## 5. Observed Operational Constraints & Limitations

- `bake_layer` rejects locked source groups (`Choose an unlocked static paint/group layer`), so workflows duplicating a locked lineart group must unlock the duplicate copy via `set_layer` before baking.
- `edit_batch` only accepts pixel/selection/layer-creation tools (`create_layer`, `bake_layer`, `select_content`, `select_polygon`, `set_selection`, `draw`, `draw_brush`, `mask_layer`, etc.), while `set_layer`, `duplicate_layer`, `move_layer`, `merge_layer_down`, and `delete_layer` must be invoked as standalone tool calls.
- Krita MCP enforces a `256 MiB` live pixel undo cap (`history_full`) and `64` edits max per `edit_batch`; large multi-region documents should union seeds per material before `set_selection(grow)`, use tight `fill_rect` bounding boxes, and save milestones cleanly.
- Indexed/palette PNGs and 16-bit PNGs are outside `scripts/png_io.py`'s scope (expects 8-bit non-interlaced Grayscale, Grayscale+Alpha, RGB, or RGBA PNGs exported by Krita).
