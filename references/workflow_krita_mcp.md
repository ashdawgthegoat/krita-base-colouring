# Krita MCP Operations & Tool Choreography

Patterns verified against Krita `6.0.4` + `krita-mcp v1.7.0`.

## 1. Standalone Tools vs `edit_batch` Allowlist

`edit_batch` executes up to **64 operations** as a single native Undo step with automatic rollback on error (`"rollback_on_error": true`), but only accepts pixel/selection/layer-creation primitives (`create_layer`, `bake_layer`, `select_content`, `select_polygon`, `set_selection`, `draw`, `draw_brush`, `mask_layer`, `apply_filter`, `selection_to_layer`, etc.).

Call these stack/state operations **outside** `edit_batch`:
- `set_layer` (locking groups, hiding `Fill_Assist_Hidden` or `Background`, opacity/blend changes)
- `duplicate_layer`, `move_layer`, `merge_layer_down`, `delete_layer`
- `inspect_document`, `export_layers`, `export_document`, `save_document`
- `undo`, `close_document`

## 2. Building `Fill_Assist_Hidden/Lineart_Fill_Reference`

When preparing the non-destructive fill reference from a locked original lineart group:
1. Lock the original lineart group (`set_layer(layer="...", locked=true)`).
2. `duplicate_layer(layer="Original_Lineart", name="Lineart_Temp_Copy")`.
3. **Unlock the duplicate** (`set_layer(layer="Lineart_Temp_Copy", locked=false)`): `bake_layer` rejects locked source layers.
4. `bake_layer(layer="Lineart_Temp_Copy", name="Lineart_Fill_Reference")`.
5. `delete_layer(layer="Lineart_Temp_Copy")` (clean up the hidden duplicate group).
6. Create `Fill_Assist_Hidden` (`visible: false`) and `move_layer(layer="Lineart_Fill_Reference", parent="Fill_Assist_Hidden")`.

To inspect `Lineart_Fill_Reference` pixels without toggling canvas visibility, use:
```json
{
  "tool": "export_layers",
  "arguments": {
    "document": 0,
    "layers": ["Fill_Assist_Hidden/Lineart_Fill_Reference"],
    "directory": "/abs/path/to/export_dir",
    "trim": false
  }
}
```
Setting `trim: false` writes an uncropped full-canvas RGBA PNG (`mutated: false`).

## 3. Fill Tool Execution via `select_content` + `grow` + `fill_rect`

Exact parameters used for lineart-bounded filling on a transparent lineart reference layer:
- `select_content`: `mode="contiguous"`, `channel="alpha"`, `threshold=1`, `tolerance=3`, `layer="Fill_Assist_Hidden/Lineart_Fill_Reference"`, `x`, `y`, `combine="replace"` (first pocket) or `"add"` (additional pockets of the same material).
- `set_selection`: `mode="grow"`, `amount=1` (`2` px for thick heavy brush ink) so base paint tucks underneath semi-transparent stroke fringes without leaving white halos.
- `draw`: single `{"type": "fill_rect", "x": ..., "y": ..., "w": ..., "h": ..., "color": "#rrggbb"}` tightly enclosing the union bbox of the filled material pockets (computed via `union_bboxes` in [krita_batch_builder.py](../scripts/krita_batch_builder.py)).
- Always end batches with `set_selection(mode="none")` (`deselect`) so subsequent edits do not accidentally stay clipped.

## 4. Undo-History & Memory Hygiene (`256 MiB` Cap)

Krita MCP caps live pixel undo memory at **256 MiB** per session/document (`history_full`). Avoid exhausting it prematurely:
- Union same-material `select_content` seeds **before** calling `set_selection(grow)` and **one** `draw(fill_rect)`, rather than issuing separate `fill_rect` calls per seed.
- Keep `fill_rect` tightly bounded to the selected regions' `union_bboxes` rather than full-canvas `(0, 0, W, H)` fills.
- Save `.kra` milestones cleanly via `save_document` (`modified: false`) after finishing Stage B or large material groups.
