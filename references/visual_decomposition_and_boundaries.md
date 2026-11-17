# Stage A & B Guide — Visual Decomposition and Boundary Preparation

## Stage A: Building a Reliable Region Map

Inspect the entire illustration at full resolution **plus** zoomed crops covering intricate regions (heads/eyes/hair locks, joints/overlaps, small props, trim seams).

Record for every identified zone:
1. **Semantic Layer Name**: Material-driven (`<Object_or_Material>_Base`, e.g., `Skin_Base`, `Glass_Panel_Base`, `Outer_Coat_Base`). Group multiple separated pieces of the *same* material onto one semantic layer unless independent editing is needed.
2. **Boundary Analysis**:
   - Inked boundaries vs un-inked colour borders (overlapping flaps, rim creases, highlight splits inside irises).
   - Tight choke points where line strokes thin out (`alpha` fades below 100).
3. **Intentional Negative Spaces (`DO_NOT_FILL`)**:
   - Exterior canvas, closed handle loops, arm-to-torso air gaps, spaces between crossed limbs/tails, hatch negative spaces. Record explicit coordinates inside each negative space so Stage B & E scripts verify they stay empty.
4. **Colour Source Rules**:
   - Prefer user-supplied hex swatches or palette references.
   - When using a colour/style reference whose proportions or clothing layout shifted slightly from the lineart, **always anchor boundaries to the structural lineart**. Flag or ask the user when palette assignment for an unreferenced element is uncertain.

---

## Stage B: Hidden Lineart Fill Reference & Minimal Gap Sealing

### Why Never Edit Original Lineart?
Closing leaks directly on original ink layers thickens delicate line endings, fills feather tips, and alters the artist's line weights. Instead:
- Lock original linework (`locked: true`).
- Bake/merge a duplicate copy onto `Fill_Assist_Hidden/Lineart_Fill_Reference` and keep `Fill_Assist_Hidden` `visible: false`.
- Krita's `select_content(mode="contiguous", layer="Fill_Assist_Hidden/Lineart_Fill_Reference", ...)` reads pixel data from hidden layers reliably, so the helper never changes the rendered composite.

### Diagnosing Gaps Without Blind Closing

Run [lineart_fill_diagnostics.py](../scripts/lineart_fill_diagnostics.py):
1. **Validate candidate seeds (`check_seeds`)**: Never pass an opaque pixel (`alpha > 3`) to Krita `select_content`—contiguous selection on ink selects only `[x, y, 1, 1]` or selects ink lines instead of the empty interior.
2. **Trace leaks (`find_leak_bottlenecks`)**: Pass a region seed (`--leak-from`) and either background (`(0, 0)`) or a neighboring material/air-gap seed (`--leak-to`). The tool reports `narrowest_span` and ink-anchored bridge candidates `(bridge_x1, bridge_y1, bridge_x2, bridge_y2)`.
3. **Visual Guard Before Sealing**:
   - Inspect every bottleneck above `3–4 px` visually against the structural artwork before drawing a bridge.
   - **Never flatten curved seams**: When separating overlapping forms across an arched boundary (such as a rolled sleeve/pant cuff over a limb, or collar overlap), place small seals along the actual curved ink contour ends rather than cutting a straight horizontal line across open space.
   - Re-export `Lineart_Fill_Reference` (`export_layers(trim=false)`) and re-run `find_leak_bottlenecks` until all material compartments return `status: "separated"`.
