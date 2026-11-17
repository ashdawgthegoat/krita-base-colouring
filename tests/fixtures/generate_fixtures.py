"""Generate deterministic synthetic RGBA fixtures for offline krita-base-colouring tests."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from png_io import write_png_rgba  # noqa: E402


def _put_px(buf: bytearray, w: int, h: int, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
    if 0 <= x < w and 0 <= y < h:
        idx = (y * w + x) * 4
        buf[idx], buf[idx + 1], buf[idx + 2], buf[idx + 3] = rgba


def _draw_rect_border(
    buf: bytearray,
    w: int,
    h: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    thickness: int = 2,
    rgba: tuple[int, int, int, int] = (0, 0, 0, 255),
) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if (x - x0 < thickness) or (x1 - x < thickness) or (y - y0 < thickness) or (y1 - y < thickness):
                _put_px(buf, w, h, x, y, rgba)


def _draw_hline(buf: bytearray, w: int, h: int, x0: int, x1: int, y: int, rgba: tuple[int, int, int, int]) -> None:
    for x in range(x0, x1 + 1):
        _put_px(buf, w, h, x, y, rgba)


def _draw_vline(buf: bytearray, w: int, h: int, x: int, y0: int, y1: int, rgba: tuple[int, int, int, int]) -> None:
    for y in range(y0, y1 + 1):
        _put_px(buf, w, h, x, y, rgba)


def _build_lineart_buffer(sealed: bool) -> tuple[int, int, bytearray]:
    w, h = 160, 120
    buf = bytearray(w * h * 4)  # fully transparent
    ink = (0, 0, 0, 255)

    # Outer main housing (20..139, 15..104)
    _draw_rect_border(buf, w, h, 20, 15, 139, 104, thickness=2, rgba=ink)
    # Intentional negative-space cutout inside housing (28..48, 35..84)
    _draw_rect_border(buf, w, h, 28, 35, 48, 84, thickness=2, rgba=ink)
    # Internal vertical material seam splitting Left_Body (x=55..88) vs Right_Body (x=91..138)
    _draw_vline(buf, w, h, 89, 15, 104, ink)
    _draw_vline(buf, w, h, 90, 15, 104, ink)
    # Small soft anti-aliased jewel aperture inside Right_Body (106..126, 48..64)
    _draw_rect_border(buf, w, h, 106, 48, 126, 64, thickness=2, rgba=ink)
    # Soft interior AA halo pixel ring inside jewel (alpha=90, still < tolerance 100 but > threshold 3)
    _draw_rect_border(buf, w, h, 108, 50, 124, 62, thickness=1, rgba=(0, 0, 0, 90))

    if not sealed:
        # Deliberate 3px gap on top border at x=64..66 (Left_Body -> background leak)
        for y in (15, 16):
            for x in (64, 65, 66):
                _put_px(buf, w, h, x, y, (0, 0, 0, 0))
        # Deliberate 2px gap in internal seam at y=58..59 (Left_Body -> Right_Body leak)
        for y in (58, 59):
            for x in (89, 90):
                _put_px(buf, w, h, x, y, (0, 0, 0, 0))
    return w, h, buf


def _fill_rect_rgba(buf: bytearray, w: int, h: int, x0: int, y0: int, x1: int, y1: int, rgba: tuple[int, int, int, int]) -> None:
    for y in range(max(0, y0), min(h, y1 + 1)):
        for x in range(max(0, x0), min(w, x1 + 1)):
            idx = (y * w + x) * 4
            buf[idx], buf[idx + 1], buf[idx + 2], buf[idx + 3] = rgba


def generate_all(out_dir: Path | None = None) -> Path:
    """Create all synthetic fixture PNGs and return the fixture directory path."""
    target = out_dir or Path(__file__).resolve().parent
    target.mkdir(parents=True, exist_ok=True)

    w, h, broken = _build_lineart_buffer(sealed=False)
    write_png_rgba(target / "synthetic_broken_lineart.png", w, h, broken)

    _, _, sealed = _build_lineart_buffer(sealed=True)
    write_png_rgba(target / "synthetic_sealed_lineart.png", w, h, sealed)

    # Clean cutout (Background hidden): Left_Body pale ivory #FFFFFF (tests pure-white safety!),
    # Right_Body slate #4A6888, Soft_Eye_Jewel gold #E6B422, Aperture (28..48, 35..84) stays alpha=0.
    cutout = bytearray(w * h * 4)
    _fill_rect_rgba(cutout, w, h, 21, 16, 89, 103, (255, 255, 255, 255))
    # Clear intentional negative-space cutout aperture interior (30..46, 37..82)
    _fill_rect_rgba(cutout, w, h, 30, 37, 46, 82, (0, 0, 0, 0))
    _fill_rect_rgba(cutout, w, h, 90, 16, 138, 103, (74, 104, 136, 255))
    _fill_rect_rgba(cutout, w, h, 108, 50, 124, 62, (230, 180, 34, 255))
    # Overlay sealed ink lines on top
    for idx in range(0, w * h * 4, 4):
        if sealed[idx + 3] > 0:
            a = sealed[idx + 3]
            cutout[idx] = (cutout[idx] * (255 - a)) // 255
            cutout[idx + 1] = (cutout[idx + 1] * (255 - a)) // 255
            cutout[idx + 2] = (cutout[idx + 2] * (255 - a)) // 255
            cutout[idx + 3] = max(cutout[idx + 3], a)
    write_png_rgba(target / "synthetic_clean_cutout.png", w, h, cutout)

    # Composite on white ground + leave an intentional 6x6 unfilled hole inside Right_Body (x=110..115, y=80..85)
    comp_hole = bytearray(w * h * 4)
    for idx in range(0, w * h * 4, 4):
        a = cutout[idx + 3]
        comp_hole[idx] = (cutout[idx] * a + 255 * (255 - a)) // 255
        comp_hole[idx + 1] = (cutout[idx + 1] * a + 255 * (255 - a)) // 255
        comp_hole[idx + 2] = (cutout[idx + 2] * a + 255 * (255 - a)) // 255
        comp_hole[idx + 3] = 255
    _fill_rect_rgba(comp_hole, w, h, 110, 80, 115, 85, (255, 255, 255, 255))
    write_png_rgba(target / "synthetic_composite_with_hole.png", w, h, comp_hole)

    # Leaked cutout: background corner (4, 4) accidentally contaminated
    leaked = bytearray(cutout)
    _fill_rect_rgba(leaked, w, h, 0, 0, 12, 12, (200, 120, 120, 255))
    write_png_rgba(target / "synthetic_leaked_cutout.png", w, h, leaked)
    return target


if __name__ == "__main__":
    out = generate_all()
    print("Generated synthetic fixtures in", out)
