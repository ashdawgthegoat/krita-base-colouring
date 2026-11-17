---
name: krita-base-colouring
description: >-
  Automate the base-colouring stage of digital illustrations inside live Krita using
  vision-first visual decomposition, non-destructive fill-reference gap repair, native
  Krita Fill Tool workflows (contiguous alpha selection + controlled selection growth),
  clean semantic Base_Colours layer organisation, and multi-scale verification. Activate
  when asked to flat-colour or base-colour lineart in Krita across any subject, style,
  or resolution. Stops after verified flat base colours without starting shading or rendering.
---

# Universal Krita Base Colouring

A general-purpose, vision-first workflow for producing flat, leak-free, independently editable base colours inside Krita while preserving the source linework completely untouched. It is canvas-size-independent, subject-agnostic, and ends cleanly once base colours are verified.

Read the supporting configs and reference guides as needed:
- Defaults & MCP limits: [default_fill_config.json](./configs/default_fill_config.json)
- Layer conventions: [layer_naming_conventions.json](./configs/layer_naming_conventions.json)
- Visual & boundary playbook: [visual_decomposition_and_boundaries.md](./references/visual_decomposition_and_boundaries.md)
- Krita MCP tool choreography: [workflow_krita_mcp.md](./references/workflow_krita_mcp.md)
- Recovery & Stage E audit guide: [verification_and_recovery.md](./references/verification_and_recovery.md)

---

## Core Invariants

1. **Preserve original linework**: Keep original lineart layers/groups locked (`locked: true`), visible on top, and completely unedited.
2. **Non-destructive gap repairs**: Close leaks only on a duplicate, hidden helper paint layer (`Fill_Assist_Hidden/Lineart_Fill_Reference`, `visible: false`).
3. **Fill Tool first**: Use native Krita contiguous fill (`select_content(mode="contiguous")` + `set_selection(mode="grow")` + tight `draw(fill_rect)`) as the primary method. Never default to manual brush painting for large base regions.
4. **Never conceal failed fills**: On any leak or overflow, immediately `undo`, diagnose the root gap or seed failure, repair or fall back intentionally (`select_polygon` / mask), and retry.
5. **Base colouring only**: Stop after saving verified flat colours and exporting the full-resolution preview. Do not paint cel shadows, gradients, halftones, rim lights, or backgrounds.

---

## Workflow Sequence

### Stage A — Visual Decomposition

Inspect the full artwork and zoomed detail crops visually before making any layer or pixel change.

1. **Identify**:
   - Distinct objects and material surfaces.
   - Inter-material boundaries (e.g., garment vs skin, trim vs body, prop vs hand).
   - Internal colour divisions within an object (e.g., iris/sclera/pupil, sole vs upper, pattern panels).
   - Small, narrow, overlapping, or softly anti-aliased areas prone to fill failure.
   - **Intentional negative spaces** (canvas exterior, enclosed limb/handle cutouts, arch apertures, hatch voids) marked `DO_NOT_FILL`.
2. **Build a Region Map** listing each semantic layer name, target regions, interior sample coordinates, neighboring boundaries, negative spaces, and intended hex colour.
3. **Resolve colours**: Use a supplied palette or colour reference. If a colour reference has slightly shifted proportions compared to the structural lineart, follow the **structural lineart contours** for placement. Ask for user approval or flag uncertainty before guessing ambiguous material colours.

### Stage B — Boundary Preparation

1. Lock existing original lineart layer(s)/group(s) (`set_layer(locked=true)`).
2. Create a hidden group `Fill_Assist_Hidden` (`visible: false`). Duplicate the original lineart, unlock the copy if needed, `bake_layer` it into a single flat paint layer named `Lineart_Fill_Reference`, move it inside `Fill_Assist_Hidden`, and remove the intermediate copy.
3. Export the full-canvas `Lineart_Fill_Reference` PNG cleanly without mutating the document (`export_layers` with `trim: false`).
4. Run [lineart_fill_diagnostics.py](./scripts/lineart_fill_diagnostics.py) to validate interior seeds (`check_seeds`), scan enclosed fillable islands (`scan_enclosed_components`), and check pairwise separation vs background and negative-space cavities (`find_leak_bottlenecks`).
5. Inspect each detected bottleneck visually:
   - Repair **only** verified small contour gaps (`draw` minimal ink bridges on `Fill_Assist_Hidden/Lineart_Fill_Reference`).
   - Do **not** close intentional negative spaces or trace artificial straight cuts across curved anatomical/garment contours.
   - Re-export `Lineart_Fill_Reference` and confirm `status: "separated"` before filling.

### Stage C — Base Colouring

1. Create `Base_Colours` (`grouplayer`, `inherit_alpha: false`) stacked directly **below** locked lineart and **above** `Fill_Assist_Hidden` (`visible: false`) and `Background`.
2. Inside `Base_Colours`, create meaningful semantic `paintlayer`s matching the Region Map (`opacity: 255`, `blending_mode: "normal"`).
3. **Fill Tool First**:
   - Use [krita_batch_builder.py](./scripts/krita_batch_builder.py) or manual `edit_batch` (`<= 64` edits):
     1. `select_content(mode="contiguous", channel="alpha", layer="Fill_Assist_Hidden/Lineart_Fill_Reference", threshold=1, tolerance=3)` on verified empty seeds (`combine="replace"`, then `"add"` for sibling pockets of the same material).
     2. Inspect the returned `selection` bounding box of every step; if it jumps to the canvas border, background, or a neighbor region, `undo` immediately.
     3. Expand with `set_selection(mode="grow", amount=1)` (`2` px for very thick `>= 6` px ink) to cover anti-aliased edge fringes cleanly.
     4. Paint inside a tight `fill_rect` (`union_bboxes` padded by `4` px, not full canvas when unnecessary) onto `Base_Colours/<Material>_Base`, then clear selection (`set_selection(mode="none")`).
4. **Targeted Fallbacks & Recovery**:
   - If contiguous fill fails inside tiny soft anti-aliased compartments (such as pupils/irises, narrow beveled emblems, or un-inked transitions), use `select_polygon` (or `mask_layer`) strictly bounded underneath overlapping ink strokes, and note why fallback was needed.
   - If a pocket was filled onto the wrong material layer, use `build_clear_and_refill_batch` (clear from the wrong layer, then refill on the correct layer) so `Base_Colours` sibling core alphas stay disjoint.

### Stage D — Layer Organisation

Ensure the final document stack matches [layer_naming_conventions.json](./configs/layer_naming_conventions.json) top-to-bottom:
1. Locked original lineart group(s)/layer(s) (`visible: true`, `locked: true`).
2. `Base_Colours` group (`visible: true`, `inherit_alpha: false`) with independent semantic material layers (`mutually disjoint core alpha`).
3. `Fill_Assist_Hidden` (`visible: false`) holding `Lineart_Fill_Reference`.
4. `Background` (`paintlayer`, `visible: true`, plain ground independent from the subject).

Never flatten the document or alter unrelated pre-existing layers.

### Stage E — Verification

1. Export the composite PNG (`export_document`) and a background-hidden cutout PNG (`set_layer(Background, visible=false)` -> `export_document` -> `set_layer(Background, visible=true)`). Optionally export individual `Base_Colours` layers (`export_layers(trim=false)`).
2. Run [base_colour_audit.py](./scripts/base_colour_audit.py):
   - `audit_transparent_cutout`: verify `alpha == 0` at background corners, exterior margins, and every declared negative-space point.
   - `find_unfilled_enclosed_islands(..., transparent_img=...)`: surface any remaining enclosed unfilled pockets inside contours while avoiding false positives on pure-white base regions.
   - `audit_layer_disjointness`: verify no unintended multi-layer contamination between `Base_Colours` layers.
3. Visually inspect the full-canvas PNG and zoomed crops (`save_inspection_crop`) across key details, seams, negative spaces, and anti-aliased edges. Resolve or honestly document every tiny residual pocket.

### Stage F — Handoff

1. Confirm `Fill_Assist_Hidden` is `visible: false`, `Background` is `visible: true`, and original lineart layers remain locked and untouched.
2. Save a **separate** layered document (`save_document(path=".../<name>_base_coloured.kra")`) without overwriting the source lineart `.kra`.
3. Export a full-resolution PNG preview (`export_document(path=".../<name>_base_coloured_preview.png")`).
4. Deliver a structured summary covering the final layer hierarchy, completed regions and tools/methods used, verification results, and any unresolved regions. **Stop here.**
