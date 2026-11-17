# Stage C Recovery & Stage E Verification Playbook

## Stage C: Failure Recovery Loop

Inspect `results` returned by every `edit_batch` (`selection` bbox `[x, y, w, h]`) and inspect visual exports for each major material:

1. **Undo immediately**: If a `select_content` selection bbox unexpectedly jumps to a canvas corner (`0, 0`), canvas boundary, known negative-space cavity, or an adjacent region's bounds, call `undo(count=1)`. Never brush over or erase leaks by hand as a substitute for sealing.
2. **Diagnose the root cause**:
   - *Selection returned `[x, y, 1, 1]`*: Seed landed on anti-aliased/opaque ink (`alpha > 3`). Re-pick a verified empty pixel via `check_seeds`.
   - *Leak to background or neighbor*: Run `find_leak_bottlenecks` on exported `Lineart_Fill_Reference.png` to locate the exact 1–6 px break, verify visually, and bridge it on `Fill_Assist_Hidden/Lineart_Fill_Reference`.
   - *Cross-material bleed discovered later*: First seal the leak on `Lineart_Fill_Reference`, then run `build_clear_and_refill_batch` (`select_content` on the sealed pocket -> `draw(clear)` on the wrong layer -> `grow(1)` -> `draw(fill_rect)` on the correct layer) so sibling core alphas stay disjoint.
   - *Tiny semi-transparent closed pockets fail at `tolerance=3`* (e.g., pupils/scleras bounded by soft eyelashes or pale translucent bevel rings): Either test a constrained higher `tolerance` (`~40–100`) while checking the bbox strictly stays inside the eye/inset bounds, or switch to `select_polygon` anchored strictly beneath the top opaque ink strokes.

---

## Stage E: Multi-Scale Audit & Verification

### 1. Deterministic Transparency & Disjointness Audit

1. Export the background-hidden transparent cutout (`set_layer(Background, visible=false)` -> `export_document` -> restore `set_layer(Background, visible=true)`).
2. Export full white-background composite (`export_document`).
3. Export individual `Base_Colours` material layers cleanly with `export_layers(trim=false)`.
4. Run [base_colour_audit.py](../scripts/base_colour_audit.py) (`--transparent`, `--composite`, `--empty-pt` for corners + negative-space coordinates):
   - **Pass criteria**:
     - `contaminated_empty_points == 0`
     - `exterior_nonzero_alpha_pixels == 0` outside the subject bounding silhouette
     - Pairwise solid-core overlap (`audit_layer_disjointness`, `alpha >= 200`) between sibling `Base_Colours` layers == `0` (`1` px `grow` overlap behind shared black ink lines is expected only inside thin `alpha < 200` edges, or `clear` interior sub-masks beneath upper layers)
     - Every reported enclosed unfilled island (`min_pixels >= 6`) either belongs to an intentional negative space, gets topped off cleanly, or is documented explicitly as unresolved (e.g., `< 5` px sub-stroke pinhole or unclosed hairline tip).

### 2. Visual Multi-Scale Inspection

Use `save_inspection_crop` (or Krita zoom crops) to inspect:
- Full-canvas silhouette on both plain white background and checkerboard transparent composite.
- Close-up `2×`–`4×` crops around fine facial/detail apertures, material seams, pocket/cuff edges, and negative-space loops to verify zero white anti-aliasing halos and zero colour spill.
