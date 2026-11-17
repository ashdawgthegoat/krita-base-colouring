"""Post-fill verification helpers for transparency isolation, unfilled islands, overlap, and crops."""

from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from .png_io import PngImage, crop_png_rgba, read_png_rgba, write_png_rgba
except ImportError:  # pragma: no cover - direct script execution fallback
    from png_io import PngImage, crop_png_rgba, read_png_rgba, write_png_rgba


@dataclass(frozen=True)
class CutoutAudit:
    """Result of auditing a background-hidden transparent cutout PNG."""

    width: int
    height: int
    checked_empty_points: List[Dict[str, object]]
    contaminated_empty_points: int
    exterior_nonzero_alpha_pixels: int
    subject_opaque_pixels: int
    passed: bool


@dataclass(frozen=True)
class UnfilledIsland:
    """Enclosed near-white unfilled pocket found inside the composite render."""

    seed: Tuple[int, int]
    pixel_count: int
    bbox: Tuple[int, int, int, int]


@dataclass(frozen=True)
class OverlapPair:
    """Pairwise solid-alpha overlap count between two Base_Colours material layers."""

    layer_a: str
    layer_b: str
    overlap_pixels: int
    sample_coord: Optional[Tuple[int, int]]


def audit_transparent_cutout(
    transparent_img: PngImage,
    expected_empty_points: Sequence[Tuple[int, int]] = ((0, 0),),
    exterior_margin_bbox: Optional[Tuple[int, int, int, int]] = None,
    alpha_zero_tolerance: int = 0,
) -> CutoutAudit:
    """Verify background corners/negative spaces stay transparent and count exterior leaks."""
    w, h, buf = transparent_img.width, transparent_img.height, transparent_img.rgba
    checked: List[Dict[str, object]] = []
    bad_pts = 0
    for x, y in expected_empty_points:
        if not (0 <= x < w and 0 <= y < h):
            continue
        r, g, b, a = transparent_img.pixel_rgba(x, y)
        ok = a <= alpha_zero_tolerance
        if not ok:
            bad_pts += 1
        checked.append({"x": x, "y": y, "rgba": [r, g, b, a], "empty": ok})

    exterior_bad = 0
    subject_opaque = 0
    if exterior_margin_bbox is not None:
        bx0, by0, bx1, by1 = exterior_margin_bbox
    else:
        bx0, by0, bx1, by1 = 0, 0, w, h

    for y in range(h):
        row_off = y * w * 4
        in_y = by0 <= y < by1
        for x in range(w):
            a = buf[row_off + x * 4 + 3]
            if a > alpha_zero_tolerance:
                subject_opaque += 1
                if exterior_margin_bbox is not None and not (in_y and bx0 <= x < bx1):
                    exterior_bad += 1

    return CutoutAudit(
        width=w,
        height=h,
        checked_empty_points=checked,
        contaminated_empty_points=bad_pts,
        exterior_nonzero_alpha_pixels=exterior_bad,
        subject_opaque_pixels=subject_opaque,
        passed=(bad_pts == 0 and exterior_bad == 0),
    )


def find_unfilled_enclosed_islands(
    composite_img: PngImage,
    background_seeds: Sequence[Tuple[int, int]] = ((0, 0),),
    negative_space_seeds: Sequence[Tuple[int, int]] = (),
    white_lum_threshold: int = 245,
    min_pixels: int = 6,
    roi_bbox: Optional[Tuple[int, int, int, int]] = None,
    max_islands: int = 100,
    transparent_img: Optional[PngImage] = None,
    empty_alpha_max: int = 3,
) -> List[UnfilledIsland]:
    """Locate enclosed unfilled pockets while skipping background and negative spaces.

    When ``transparent_img`` (exported with ``Background`` hidden) is supplied, emptiness is
    tested via ``alpha <= empty_alpha_max`` so genuinely painted pure-white bases are never
    misreported as unfilled holes.
    """
    w, h, buf = composite_img.width, composite_img.height, composite_img.rgba
    if transparent_img is not None:
        if transparent_img.width != w or transparent_img.height != h:
            raise ValueError(f"transparent_img {transparent_img.width}x{transparent_img.height} != {w}x{h}")
        t_buf = transparent_img.rgba

        def _is_unfilled(idx: int) -> bool:
            return t_buf[idx * 4 + 3] <= empty_alpha_max

    else:

        def _is_unfilled(idx: int) -> bool:
            off = idx * 4
            return (buf[off] + buf[off + 1] + buf[off + 2]) >= white_lum_threshold * 3

    visited = bytearray(w * h)

    def _flood(start_idx: int) -> Tuple[int, Tuple[int, int, int, int]]:
        q = deque([start_idx])
        visited[start_idx] = 1
        sx = start_idx % w
        sy = start_idx // w
        min_x = max_x = sx
        min_y = max_y = sy
        cnt = 0
        while q:
            idx = q.popleft()
            cnt += 1
            x = idx % w
            y = idx // w
            if x < min_x:
                min_x = x
            elif x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            elif y > max_y:
                max_y = y
            for nidx in (
                idx + 1 if x + 1 < w else -1,
                idx - 1 if x > 0 else -1,
                idx + w if y + 1 < h else -1,
                idx - w if y > 0 else -1,
            ):
                if nidx >= 0 and not visited[nidx] and _is_unfilled(nidx):
                    visited[nidx] = 1
                    q.append(nidx)
        return cnt, (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)

    for bx, by in tuple(background_seeds) + tuple(negative_space_seeds):
        if 0 <= bx < w and 0 <= by < h:
            idx = by * w + bx
            if not visited[idx] and _is_unfilled(idx):
                _flood(idx)

    if roi_bbox is None:
        x0, y0, x1, y1 = 0, 0, w, h
    else:
        x0 = max(0, roi_bbox[0])
        y0 = max(0, roi_bbox[1])
        x1 = min(w, roi_bbox[2])
        y1 = min(h, roi_bbox[3])

    islands: List[UnfilledIsland] = []
    for y in range(y0, y1):
        row_off = y * w
        for x in range(x0, x1):
            idx = row_off + x
            if not visited[idx] and _is_unfilled(idx):
                cnt, bbox = _flood(idx)
                if cnt >= min_pixels:
                    islands.append(UnfilledIsland(seed=(x, y), pixel_count=cnt, bbox=bbox))

    islands.sort(key=lambda item: (-item.pixel_count, item.seed[1], item.seed[0]))
    return islands[:max_islands]


def audit_layer_disjointness(
    layer_images: Dict[str, PngImage],
    alpha_threshold: int = 200,
) -> List[OverlapPair]:
    """Check pairwise opaque pixel overlap across Base_Colours material layers."""
    names = sorted(layer_images.keys())
    if not names:
        return []
    first = layer_images[names[0]]
    w, h = first.width, first.height
    for name in names[1:]:
        img = layer_images[name]
        if img.width != w or img.height != h:
            raise ValueError(f"Layer {name!r} dimensions {img.width}x{img.height} differ from {w}x{h}")

    alphas = {name: layer_images[name].extract_alpha() for name in names}
    overlaps: List[OverlapPair] = []
    total_px = w * h
    for i, a_name in enumerate(names):
        a_buf = alphas[a_name]
        for b_name in names[i + 1 :]:
            b_buf = alphas[b_name]
            cnt = 0
            sample: Optional[Tuple[int, int]] = None
            for idx in range(total_px):
                if a_buf[idx] >= alpha_threshold and b_buf[idx] >= alpha_threshold:
                    cnt += 1
                    if sample is None:
                        sample = (idx % w, idx // w)
            if cnt > 0:
                overlaps.append(OverlapPair(layer_a=a_name, layer_b=b_name, overlap_pixels=cnt, sample_coord=sample))
    return overlaps


def save_inspection_crop(
    image_path: str | Path,
    out_path: str | Path,
    bbox: Tuple[int, int, int, int],
    scale: int = 2,
    checkerboard: bool = False,
) -> Path:
    """Write a clean integer-zoomed inspection crop to disk for close-up visual audit."""
    img = read_png_rgba(image_path)
    crop = crop_png_rgba(img, bbox=bbox, scale=scale, composite_checkerboard=checkerboard)
    return write_png_rgba(out_path, crop.width, crop.height, crop.rgba)


def _parse_pt(raw: str) -> Tuple[int, int]:
    parts = [int(v.strip()) for v in raw.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected x,y coordinate, got {raw!r}")
    return parts[0], parts[1]


def _main() -> None:
    parser = argparse.ArgumentParser(description="Audit Base_Colours transparent cutouts and unfilled pockets.")
    parser.add_argument("--transparent", help="Path to Background-hidden transparent PNG export")
    parser.add_argument("--composite", help="Path to full white-background composite PNG export")
    parser.add_argument("--empty-pt", action="append", type=_parse_pt, default=[], help="Expected transparent point x,y (repeatable)")
    parser.add_argument("--min-pixels", type=int, default=6, help="Minimum unfilled island size to report")
    parser.add_argument("--white-threshold", type=int, default=245, help="Mean RGB threshold for unfilled white areas")
    args = parser.parse_args()

    result: Dict[str, object] = {}
    empty_pts = tuple(args.empty_pt) if args.empty_pt else ((0, 0),)
    if args.transparent:
        timg = read_png_rgba(args.transparent)
        result["cutout_audit"] = asdict(audit_transparent_cutout(timg, expected_empty_points=empty_pts))
    if args.composite:
        cimg = read_png_rgba(args.composite)
        islands = find_unfilled_enclosed_islands(
            cimg,
            background_seeds=(empty_pts[0],),
            negative_space_seeds=empty_pts[1:],
            white_lum_threshold=args.white_threshold,
            min_pixels=args.min_pixels,
        )
        result["unfilled_island_count"] = len(islands)
        result["unfilled_islands"] = [asdict(i) for i in islands]

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
