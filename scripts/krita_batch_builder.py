"""Schema-safe Krita MCP edit_batch payload helpers for base colouring."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple


MAX_BATCH_EDITS = 64


def clamp_rect(x: int, y: int, w: int, h: int, canvas_width: int, canvas_height: int) -> Tuple[int, int, int, int]:
    """Clamp rectangle [x, y, w, h] strictly within [0, canvas_width) x [0, canvas_height)."""
    x0 = max(0, int(x))
    y0 = max(0, int(y))
    x1 = min(int(canvas_width), int(x) + max(0, int(w)))
    y1 = min(int(canvas_height), int(y) + max(0, int(h)))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"Clamped rect is empty for ({x}, {y}, {w}, {h}) on {canvas_width}x{canvas_height}")
    return x0, y0, x1 - x0, y1 - y0


def union_bboxes(
    bboxes: Sequence[Tuple[int, int, int, int]],
    pad: int = 4,
    canvas_size: Optional[Tuple[int, int]] = None,
) -> Tuple[int, int, int, int]:
    """Compute tight enclosing [x, y, w, h] over multiple region bboxes with padding."""
    if not bboxes:
        raise ValueError("bboxes must contain at least one rectangle")
    min_x = min(b[0] for b in bboxes) - pad
    min_y = min(b[1] for b in bboxes) - pad
    max_x = max(b[0] + b[2] for b in bboxes) + pad
    max_y = max(b[1] + b[3] for b in bboxes) + pad
    if canvas_size is not None:
        return clamp_rect(min_x, min_y, max_x - min_x, max_y - min_y, canvas_size[0], canvas_size[1])
    return min_x, min_y, max_x - min_x, max_y - min_y


def build_seal_gaps_batch(
    bridges: Sequence[Tuple[int, int, int, int]],
    lineart_ref_layer: str = "Fill_Assist_Hidden/Lineart_Fill_Reference",
    stroke_width: float = 2.5,
    color: str = "#000000",
    document: int = 0,
    label: str = "Seal boundary gaps on hidden fill reference",
) -> Dict[str, object]:
    """Build a draw payload closing small contour gaps (x1, y1, x2, y2) on Lineart_Fill_Reference."""
    if not bridges:
        raise ValueError("bridges must contain at least one (x1, y1, x2, y2) segment")
    commands = [
        {"type": "line", "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2), "color": color, "stroke_width": float(stroke_width)}
        for x1, y1, x2, y2 in bridges
    ]
    return {
        "document": document,
        "label": label,
        "results": "summary",
        "edits": [{"tool": "draw", "arguments": {"layer": lineart_ref_layer, "commands": commands}}],
    }


def build_contiguous_fill_batches(
    target_layer: str,
    color: str,
    seeds: Sequence[Tuple[int, int]],
    fill_bbox: Tuple[int, int, int, int],
    grow_px: int = 1,
    lineart_ref_layer: str = "Fill_Assist_Hidden/Lineart_Fill_Reference",
    threshold: int = 1,
    tolerance: int = 3,
    document: int = 0,
    max_edits: int = MAX_BATCH_EDITS,
    label_prefix: str = "Fill enclosed regions",
) -> List[Dict[str, object]]:
    """Build chunked Krita MCP edit_batch payloads respecting Krita's 64-edit limit."""
    if not seeds:
        raise ValueError("seeds must contain at least one interior (x, y) point")
    # Reserve 3 trailing edits per batch: optional set_selection(grow) + draw(fill_rect) + set_selection(none)
    reserved = 3 if grow_px > 0 else 2
    max_seeds_per_batch = max(1, min(max_edits, MAX_BATCH_EDITS) - reserved)

    fx, fy, fw, fh = fill_bbox
    batches: List[Dict[str, object]] = []
    for chunk_idx in range(0, len(seeds), max_seeds_per_batch):
        chunk = seeds[chunk_idx : chunk_idx + max_seeds_per_batch]
        edits: List[Dict[str, object]] = []
        for idx, (sx, sy) in enumerate(chunk):
            edits.append(
                {
                    "tool": "select_content",
                    "arguments": {
                        "layer": lineart_ref_layer,
                        "mode": "contiguous",
                        "channel": "alpha",
                        "x": int(sx),
                        "y": int(sy),
                        "threshold": int(threshold),
                        "tolerance": int(tolerance),
                        "combine": "replace" if idx == 0 else "add",
                    },
                }
            )
        if grow_px > 0:
            edits.append({"tool": "set_selection", "arguments": {"mode": "grow", "amount": int(grow_px)}})
        edits.append(
            {
                "tool": "draw",
                "arguments": {
                    "layer": target_layer,
                    "commands": [{"type": "fill_rect", "x": int(fx), "y": int(fy), "w": int(fw), "h": int(fh), "color": color}],
                },
            }
        )
        edits.append({"tool": "set_selection", "arguments": {"mode": "none"}})
        batches.append(
            {
                "document": document,
                "label": f"{label_prefix} ({len(batches) + 1})",
                "results": "summary",
                "edits": edits,
            }
        )
    return batches


def build_polygon_fill_batch(
    target_layer: str,
    color: str,
    polygons: Sequence[Sequence[Sequence[float]]],
    grow_px: int = 0,
    antialias: bool = True,
    document: int = 0,
    label: str = "Fill polygonal region",
) -> Dict[str, object]:
    """Build an edit_batch using select_polygon fallback for soft/complex sub-regions."""
    if not polygons:
        raise ValueError("polygons must contain at least one point sequence")
    all_pts = [pt for poly in polygons for pt in poly]
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    pad = max(2, int(grow_px) + 2)
    fx = int(min(xs)) - pad
    fy = int(min(ys)) - pad
    fw = int(max(xs)) - fx + pad + 1
    fh = int(max(ys)) - fy + pad + 1

    edits: List[Dict[str, object]] = []
    for idx, poly in enumerate(polygons):
        edits.append(
            {
                "tool": "select_polygon",
                "arguments": {
                    "points": [[float(p[0]), float(p[1])] for p in poly],
                    "antialias": bool(antialias),
                    "combine": "replace" if idx == 0 else "add",
                },
            }
        )
    if grow_px > 0:
        edits.append({"tool": "set_selection", "arguments": {"mode": "grow", "amount": int(grow_px)}})
    edits.append(
        {
            "tool": "draw",
            "arguments": {
                "layer": target_layer,
                "commands": [{"type": "fill_rect", "x": fx, "y": fy, "w": fw, "h": fh, "color": color}],
            },
        }
    )
    edits.append({"tool": "set_selection", "arguments": {"mode": "none"}})
    if len(edits) > MAX_BATCH_EDITS:
        raise ValueError(f"Polygon batch exceeds {MAX_BATCH_EDITS} edits ({len(edits)})")
    return {"document": document, "label": label, "results": "summary", "edits": edits}


def build_clear_and_refill_batch(
    wrong_layer: str,
    correct_layer: str,
    color: str,
    seeds: Sequence[Tuple[int, int]],
    region_bbox: Tuple[int, int, int, int],
    clear_grow_px: int = 0,
    fill_grow_px: int = 1,
    lineart_ref_layer: str = "Fill_Assist_Hidden/Lineart_Fill_Reference",
    threshold: int = 1,
    tolerance: int = 3,
    document: int = 0,
    label: str = "Recover cross-material fill contamination",
) -> Dict[str, object]:
    """Select sealed compartment, clear leaked fill off wrong_layer, then fill cleanly on correct_layer."""
    if not seeds:
        raise ValueError("seeds must contain at least one point")
    rx, ry, rw, rh = region_bbox
    edits: List[Dict[str, object]] = []
    for idx, (sx, sy) in enumerate(seeds):
        edits.append(
            {
                "tool": "select_content",
                "arguments": {
                    "layer": lineart_ref_layer,
                    "mode": "contiguous",
                    "channel": "alpha",
                    "x": int(sx),
                    "y": int(sy),
                    "threshold": int(threshold),
                    "tolerance": int(tolerance),
                    "combine": "replace" if idx == 0 else "add",
                },
            }
        )
    if clear_grow_px > 0:
        edits.append({"tool": "set_selection", "arguments": {"mode": "grow", "amount": int(clear_grow_px)}})
    edits.append(
        {
            "tool": "draw",
            "arguments": {"layer": wrong_layer, "commands": [{"type": "clear", "x": int(rx), "y": int(ry), "w": int(rw), "h": int(rh)}]},
        }
    )
    delta_grow = max(0, int(fill_grow_px) - max(0, int(clear_grow_px)))
    if delta_grow > 0:
        edits.append({"tool": "set_selection", "arguments": {"mode": "grow", "amount": delta_grow}})
    edits.append(
        {
            "tool": "draw",
            "arguments": {
                "layer": correct_layer,
                "commands": [{"type": "fill_rect", "x": int(rx), "y": int(ry), "w": int(rw), "h": int(rh), "color": color}],
            },
        }
    )
    edits.append({"tool": "set_selection", "arguments": {"mode": "none"}})
    if len(edits) > MAX_BATCH_EDITS:
        raise ValueError(f"Recovery batch exceeds {MAX_BATCH_EDITS} edits ({len(edits)})")
    return {"document": document, "label": label, "results": "summary", "edits": edits}
