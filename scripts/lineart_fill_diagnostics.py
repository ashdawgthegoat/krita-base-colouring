"""Deterministic 4-connected fill-boundary and leak-bottleneck diagnostics for arbitrary RGBA lineart."""

from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from .png_io import PngImage, read_png_rgba
except ImportError:  # pragma: no cover - direct script execution fallback
    from png_io import PngImage, read_png_rgba


@dataclass(frozen=True)
class SeedStatus:
    """Validation status for a candidate contiguous fill seed coordinate."""

    x: int
    y: int
    alpha: int
    valid: bool
    reason: str


@dataclass(frozen=True)
class ComponentSummary:
    """Connected fillable component metadata returned by 4-connected tracing."""

    seed: Tuple[int, int]
    pixel_count: int
    bbox: Tuple[int, int, int, int]  # (x, y, width, height)
    touches_border: bool
    capped: bool = False


@dataclass(frozen=True)
class BottleneckPoint:
    """Narrowest empty-channel choke location along a leak path."""

    x: int
    y: int
    min_span: int
    horizontal_span: int
    vertical_span: int
    bridge_x1: int
    bridge_y1: int
    bridge_x2: int
    bridge_y2: int


@dataclass(frozen=True)
class LeakReport:
    """Separation check result between two fillable seed points."""

    source: Tuple[int, int]
    target: Tuple[int, int]
    status: str  # "separated", "leaked", "invalid_seed"
    path_length: int
    narrowest_span: Optional[int]
    bottlenecks: List[BottleneckPoint]


def check_seeds(
    alpha: bytearray,
    width: int,
    height: int,
    seeds: Iterable[Tuple[int, int]],
    empty_alpha_max: int = 3,
) -> List[SeedStatus]:
    """Validate that candidate fill seeds lie inside bounds on empty pixels (alpha <= empty_alpha_max)."""
    statuses: List[SeedStatus] = []
    for x, y in seeds:
        if not (0 <= x < width and 0 <= y < height):
            statuses.append(SeedStatus(x=x, y=y, alpha=-1, valid=False, reason="out_of_bounds"))
            continue
        val = alpha[y * width + x]
        if val > empty_alpha_max:
            statuses.append(SeedStatus(x=x, y=y, alpha=val, valid=False, reason="opaque_ink_pixel"))
        else:
            statuses.append(SeedStatus(x=x, y=y, alpha=val, valid=True, reason="ok"))
    return statuses


def _flood_indices(
    alpha: bytearray,
    width: int,
    height: int,
    start_idx: int,
    empty_alpha_max: int,
    visited: bytearray,
    cap: Optional[int] = None,
) -> Tuple[int, Tuple[int, int, int, int], bool, bool]:
    """Run 4-connected BFS starting at flat pixel index, marking global visited bytearray."""
    q = deque([start_idx])
    visited[start_idx] = 1
    sx = start_idx % width
    sy = start_idx // width
    min_x = max_x = sx
    min_y = max_y = sy
    touches_border = sx == 0 or sx == width - 1 or sy == 0 or sy == height - 1
    count = 0
    capped = False

    while q:
        idx = q.popleft()
        count += 1
        x = idx % width
        y = idx // width
        if x < min_x:
            min_x = x
        elif x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        elif y > max_y:
            max_y = y
        if x == 0 or x == width - 1 or y == 0 or y == height - 1:
            touches_border = True
        if cap is not None and count >= cap:
            capped = True
            break

        if x + 1 < width:
            ni = idx + 1
            if not visited[ni] and alpha[ni] <= empty_alpha_max:
                visited[ni] = 1
                q.append(ni)
        if x > 0:
            ni = idx - 1
            if not visited[ni] and alpha[ni] <= empty_alpha_max:
                visited[ni] = 1
                q.append(ni)
        if y + 1 < height:
            ni = idx + width
            if not visited[ni] and alpha[ni] <= empty_alpha_max:
                visited[ni] = 1
                q.append(ni)
        if y > 0:
            ni = idx - width
            if not visited[ni] and alpha[ni] <= empty_alpha_max:
                visited[ni] = 1
                q.append(ni)

    bbox = (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
    return count, bbox, touches_border, capped


def trace_component(
    alpha: bytearray,
    width: int,
    height: int,
    seed: Tuple[int, int],
    empty_alpha_max: int = 3,
    cap: Optional[int] = None,
) -> Optional[ComponentSummary]:
    """Trace one 4-connected fillable component from seed; returns None if seed is invalid or opaque."""
    status = check_seeds(alpha, width, height, [seed], empty_alpha_max=empty_alpha_max)[0]
    if not status.valid:
        return None
    visited = bytearray(width * height)
    start_idx = seed[1] * width + seed[0]
    count, bbox, touches_border, capped = _flood_indices(
        alpha, width, height, start_idx, empty_alpha_max, visited, cap=cap
    )
    return ComponentSummary(seed=seed, pixel_count=count, bbox=bbox, touches_border=touches_border, capped=capped)


def _measure_orthogonal_spans(
    alpha: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    empty_alpha_max: int,
    scan_radius: int,
) -> BottleneckPoint:
    """Measure clear horizontal and vertical spans at (x, y) and propose ink-anchored bridge endpoints."""
    left = 0
    while left < scan_radius and x - left - 1 >= 0 and alpha[y * width + (x - left - 1)] <= empty_alpha_max:
        left += 1
    right = 0
    while right < scan_radius and x + right + 1 < width and alpha[y * width + (x + right + 1)] <= empty_alpha_max:
        right += 1
    up = 0
    while up < scan_radius and y - up - 1 >= 0 and alpha[(y - up - 1) * width + x] <= empty_alpha_max:
        up += 1
    down = 0
    while down < scan_radius and y + down + 1 < height and alpha[(y + down + 1) * width + x] <= empty_alpha_max:
        down += 1

    hx = left + right + 1
    vy = up + down + 1
    if hx <= vy:
        return BottleneckPoint(
            x=x,
            y=y,
            min_span=hx,
            horizontal_span=hx,
            vertical_span=vy,
            bridge_x1=max(0, x - left - 1),
            bridge_y1=y,
            bridge_x2=min(width - 1, x + right + 1),
            bridge_y2=y,
        )
    return BottleneckPoint(
        x=x,
        y=y,
        min_span=vy,
        horizontal_span=hx,
        vertical_span=vy,
        bridge_x1=x,
        bridge_y1=max(0, y - up - 1),
        bridge_x2=x,
        bridge_y2=min(height - 1, y + down + 1),
    )


def find_leak_bottlenecks(
    alpha: bytearray,
    width: int,
    height: int,
    source_seed: Tuple[int, int],
    target_seed: Tuple[int, int],
    empty_alpha_max: int = 3,
    max_gap_width_px: int = 8,
    scan_radius: int = 20,
    max_bottlenecks: int = 12,
) -> LeakReport:
    """Check whether source_seed reaches target_seed via fillable pixels and localize narrowest chokes."""
    statuses = check_seeds(alpha, width, height, [source_seed, target_seed], empty_alpha_max=empty_alpha_max)
    if not statuses[0].valid or not statuses[1].valid:
        return LeakReport(
            source=source_seed,
            target=target_seed,
            status="invalid_seed",
            path_length=0,
            narrowest_span=None,
            bottlenecks=[],
        )

    src_idx = source_seed[1] * width + source_seed[0]
    dst_idx = target_seed[1] * width + target_seed[0]
    if src_idx == dst_idx:
        return LeakReport(
            source=source_seed,
            target=target_seed,
            status="leaked",
            path_length=1,
            narrowest_span=None,
            bottlenecks=[],
        )

    parent = [-1] * (width * height)
    visited = bytearray(width * height)
    visited[src_idx] = 1
    q = deque([src_idx])
    found = False

    while q:
        idx = q.popleft()
        if idx == dst_idx:
            found = True
            break
        x = idx % width
        y = idx // width
        for nidx in (
            idx + 1 if x + 1 < width else -1,
            idx - 1 if x > 0 else -1,
            idx + width if y + 1 < height else -1,
            idx - width if y > 0 else -1,
        ):
            if nidx >= 0 and not visited[nidx] and alpha[nidx] <= empty_alpha_max:
                visited[nidx] = 1
                parent[nidx] = idx
                q.append(nidx)

    if not found:
        return LeakReport(
            source=source_seed,
            target=target_seed,
            status="separated",
            path_length=0,
            narrowest_span=None,
            bottlenecks=[],
        )

    path: List[Tuple[int, int]] = []
    cur = dst_idx
    while cur != -1:
        path.append((cur % width, cur // width))
        if cur == src_idx:
            break
        cur = parent[cur]
    path.reverse()

    candidates: List[BottleneckPoint] = []
    min_seen: Optional[int] = None
    for idx, (px, py) in enumerate(path):
        # Step by 1 inside narrow regions, coarser not needed for short paths
        bp = _measure_orthogonal_spans(alpha, width, height, px, py, empty_alpha_max, scan_radius)
        if min_seen is None or bp.min_span < min_seen:
            min_seen = bp.min_span
        if bp.min_span <= max_gap_width_px:
            candidates.append(bp)

    # Deduplicate nearby bottleneck pixels within 3 px radius keeping narrowest first
    candidates.sort(key=lambda b: (b.min_span, b.y, b.x))
    filtered: List[BottleneckPoint] = []
    for bp in candidates:
        if all(abs(bp.x - keep.x) > 3 or abs(bp.y - keep.y) > 3 for keep in filtered):
            filtered.append(bp)
            if len(filtered) >= max_bottlenecks:
                break

    return LeakReport(
        source=source_seed,
        target=target_seed,
        status="leaked",
        path_length=len(path),
        narrowest_span=min_seen,
        bottlenecks=filtered,
    )


def scan_enclosed_components(
    alpha: bytearray,
    width: int,
    height: int,
    roi_bbox: Optional[Tuple[int, int, int, int]] = None,
    background_seeds: Sequence[Tuple[int, int]] = ((0, 0),),
    empty_alpha_max: int = 3,
    min_pixels: int = 4,
    max_components: int = 200,
) -> List[ComponentSummary]:
    """Scan all enclosed fillable components inside roi_bbox (or full canvas) excluding background_seeds."""
    visited = bytearray(width * height)
    for bx, by in background_seeds:
        if 0 <= bx < width and 0 <= by < height:
            bidx = by * width + bx
            if not visited[bidx] and alpha[bidx] <= empty_alpha_max:
                _flood_indices(alpha, width, height, bidx, empty_alpha_max, visited)

    if roi_bbox is None:
        x0, y0, x1, y1 = 0, 0, width, height
    else:
        x0 = max(0, roi_bbox[0])
        y0 = max(0, roi_bbox[1])
        x1 = min(width, roi_bbox[2])
        y1 = min(height, roi_bbox[3])

    components: List[ComponentSummary] = []
    for y in range(y0, y1):
        row_off = y * width
        for x in range(x0, x1):
            idx = row_off + x
            if not visited[idx] and alpha[idx] <= empty_alpha_max:
                count, bbox, touches_border, capped = _flood_indices(
                    alpha, width, height, idx, empty_alpha_max, visited
                )
                if count >= min_pixels:
                    components.append(
                        ComponentSummary(
                            seed=(x, y),
                            pixel_count=count,
                            bbox=bbox,
                            touches_border=touches_border,
                            capped=capped,
                        )
                    )

    components.sort(key=lambda c: (-c.pixel_count, c.seed[1], c.seed[0]))
    return components[:max_components]


def analyze_lineart_png(
    image_path: str | Path,
    roi_bbox: Optional[Tuple[int, int, int, int]] = None,
    background_seeds: Sequence[Tuple[int, int]] = ((0, 0),),
    empty_alpha_max: int = 3,
    min_pixels: int = 4,
) -> Dict[str, object]:
    """Load a lineart PNG and return enclosed component telemetry suitable for inspection."""
    img: PngImage = read_png_rgba(image_path)
    alpha = img.extract_alpha()
    comps = scan_enclosed_components(
        alpha,
        img.width,
        img.height,
        roi_bbox=roi_bbox,
        background_seeds=background_seeds,
        empty_alpha_max=empty_alpha_max,
        min_pixels=min_pixels,
    )
    return {
        "width": img.width,
        "height": img.height,
        "empty_alpha_max": empty_alpha_max,
        "component_count": len(comps),
        "components": [asdict(c) for c in comps],
    }


def _parse_pt(raw: str) -> Tuple[int, int]:
    parts = [int(v.strip()) for v in raw.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected x,y coordinate, got {raw!r}")
    return parts[0], parts[1]


def _main() -> None:
    parser = argparse.ArgumentParser(description="Inspect fillable contours and leak bottlenecks on lineart PNGs.")
    parser.add_argument("image", help="Path to Lineart_Fill_Reference RGBA PNG")
    parser.add_argument("--threshold", type=int, default=3, help="Max alpha treated as fillable empty space (default 3)")
    parser.add_argument("--min-pixels", type=int, default=4, help="Minimum component pixel count to report")
    parser.add_argument("--bg", type=_parse_pt, default=(0, 0), help="Background seed x,y (default 0,0)")
    parser.add_argument("--leak-from", type=_parse_pt, help="Source region seed x,y to check against --leak-to")
    parser.add_argument("--leak-to", type=_parse_pt, help="Target seed x,y (default matches --bg if omitted)")
    parser.add_argument("--roi", help="Optional ROI x0,y0,x1,y1")
    args = parser.parse_args()

    img = read_png_rgba(args.image)
    alpha = img.extract_alpha()

    if args.leak_from is not None:
        dst = args.leak_to if args.leak_to is not None else args.bg
        rep = find_leak_bottlenecks(alpha, img.width, img.height, args.leak_from, dst, empty_alpha_max=args.threshold)
        print(json.dumps(asdict(rep), indent=2))
        return

    roi_bbox = None
    if args.roi:
        vals = [int(v.strip()) for v in args.roi.split(",")]
        if len(vals) != 4:
            raise ValueError("--roi must be x0,y0,x1,y1")
        roi_bbox = (vals[0], vals[1], vals[2], vals[3])

    out = analyze_lineart_png(
        args.image,
        roi_bbox=roi_bbox,
        background_seeds=(args.bg,),
        empty_alpha_max=args.threshold,
        min_pixels=args.min_pixels,
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    _main()
