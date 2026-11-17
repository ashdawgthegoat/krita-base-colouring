"""Minimal pure-stdlib PNG RGBA reader, writer, cropper, and checkerboard visualizer."""

from __future__ import annotations

import binascii
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PngImage:
    """In-memory 8-bit RGBA image stored as a flat row-major bytearray."""

    width: int
    height: int
    rgba: bytearray

    def pixel_rgba(self, x: int, y: int) -> Tuple[int, int, int, int]:
        """Return (r, g, b, a) at pixel (x, y)."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"Pixel ({x}, {y}) out of bounds for {self.width}x{self.height}")
        idx = (y * self.width + x) * 4
        return (self.rgba[idx], self.rgba[idx + 1], self.rgba[idx + 2], self.rgba[idx + 3])

    def extract_alpha(self) -> bytearray:
        """Return flat W*H alpha channel bytearray."""
        return bytearray(self.rgba[3::4])


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter_scanlines(raw: bytes, width: int, height: int, channels: int) -> bytearray:
    row_bytes = width * channels
    stride = row_bytes + 1
    expected = stride * height
    if len(raw) < expected:
        raise ValueError(f"Truncated PNG IDAT payload: got {len(raw)} bytes, expected >= {expected}")
    prev = bytearray(row_bytes)
    out = bytearray(width * height * 4)

    for y in range(height):
        start = y * stride
        filt = raw[start]
        row = bytearray(raw[start + 1 : start + stride])
        if filt == 1:
            for i in range(channels, row_bytes):
                row[i] = (row[i] + row[i - channels]) & 0xFF
        elif filt == 2:
            for i in range(row_bytes):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filt == 3:
            for i in range(row_bytes):
                left = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(row_bytes):
                left = row[i - channels] if i >= channels else 0
                up_left = prev[i - channels] if i >= channels else 0
                row[i] = (row[i] + _paeth(left, prev[i], up_left)) & 0xFF
        elif filt != 0:
            raise ValueError(f"Unsupported PNG filter byte {filt} on row {y}")

        prev = row
        dst_off = y * width * 4
        if channels == 4:
            out[dst_off : dst_off + width * 4] = row
        elif channels == 3:
            for x in range(width):
                s = x * 3
                d = dst_off + x * 4
                out[d] = row[s]
                out[d + 1] = row[s + 1]
                out[d + 2] = row[s + 2]
                out[d + 3] = 255
        elif channels == 2:
            for x in range(width):
                g = row[x * 2]
                d = dst_off + x * 4
                out[d] = g
                out[d + 1] = g
                out[d + 2] = g
                out[d + 3] = row[x * 2 + 1]
        elif channels == 1:
            for x in range(width):
                g = row[x]
                d = dst_off + x * 4
                out[d] = g
                out[d + 1] = g
                out[d + 2] = g
                out[d + 3] = 255
    return out


def read_png_rgba(path: str | Path) -> PngImage:
    """Load an 8-bit non-interlaced PNG (Gray, Gray+Alpha, RGB, or RGBA) as RGBA."""
    data = Path(path).read_bytes()
    if data[:8] != _PNG_SIGNATURE:
        raise ValueError(f"Invalid PNG signature in {path}")

    pos = 8
    idat = bytearray()
    width = height = bit_depth = color_type = interlace = 0
    seen_ihdr = False

    while pos + 8 <= len(data):
        length, chunk_type = struct.unpack(">I4s", data[pos : pos + 8])
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk_data[:13])
            seen_ihdr = True
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if not seen_ihdr:
        raise ValueError(f"Missing IHDR chunk in {path}")
    if bit_depth != 8:
        raise ValueError(f"Unsupported PNG bit depth {bit_depth} in {path}; only 8-bit is supported")
    if interlace != 0:
        raise ValueError(f"Unsupported interlaced PNG in {path}")

    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    if color_type not in channels_by_type:
        raise ValueError(f"Unsupported PNG color type {color_type} in {path}; indexed/palette PNGs require RGBA conversion")

    raw = zlib.decompress(bytes(idat))
    rgba = _unfilter_scanlines(raw, width, height, channels_by_type[color_type])
    return PngImage(width=width, height=height, rgba=rgba)


def write_png_rgba(path: str | Path, width: int, height: int, rgba: bytes | bytearray) -> Path:
    """Write an 8-bit RGBA image to PNG using zlib compression."""
    expected = width * height * 4
    if len(rgba) != expected:
        raise ValueError(f"RGBA buffer length {len(rgba)} != expected {expected}")

    def _chunk(tag: bytes, payload: bytes) -> bytes:
        crc = binascii.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    raw = bytearray((width * 4 + 1) * height)
    row_len = width * 4
    mv = memoryview(rgba)
    for y in range(height):
        dst = y * (row_len + 1)
        raw[dst] = 0
        raw[dst + 1 : dst + 1 + row_len] = mv[y * row_len : (y + 1) * row_len]

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), level=6)
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b""))
    return out_path


def crop_png_rgba(
    img: PngImage,
    bbox: Tuple[int, int, int, int],
    scale: int = 1,
    composite_checkerboard: bool = False,
    checker_size: int = 8,
) -> PngImage:
    """Extract an integer-scaled crop [x0, y0, x1, y1] (clamped) from an RGBA image."""
    x0 = max(0, bbox[0])
    y0 = max(0, bbox[1])
    x1 = min(img.width, bbox[2])
    y1 = min(img.height, bbox[3])
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"Empty crop bbox {bbox} for {img.width}x{img.height}")
    scale = max(1, int(scale))
    cw = (x1 - x0) * scale
    ch = (y1 - y0) * scale
    buf = bytearray(cw * ch * 4)

    for dy in range(ch):
        sy = y0 + dy // scale
        for dx in range(cw):
            sx = x0 + dx // scale
            r, g, b, a = img.pixel_rgba(sx, sy)
            di = (dy * cw + dx) * 4
            if composite_checkerboard and a < 255:
                bg = 216 if ((dx // checker_size + dy // checker_size) % 2 == 0) else 176
                r = (r * a + bg * (255 - a)) // 255
                g = (g * a + bg * (255 - a)) // 255
                b = (b * a + bg * (255 - a)) // 255
                a = 255
            buf[di] = r
            buf[di + 1] = g
            buf[di + 2] = b
            buf[di + 3] = a
    return PngImage(width=cw, height=ch, rgba=buf)


def draw_filled_circle(
    buf: bytearray, width: int, height: int, cx: float, cy: float, radius: float, rgba: Iterable[int]
) -> None:
    """Paint a crisp pixel circle onto a flat RGBA bytearray (helpful for synthetic fixtures/previews)."""
    r, g, b, a = rgba
    r2 = radius * radius
    y0 = max(0, int(cy - radius - 1))
    y1 = min(height - 1, int(cy + radius + 1))
    x0 = max(0, int(cx - radius - 1))
    x1 = min(width - 1, int(cx + radius + 1))
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(x0, x1 + 1):
            dx = x - cx
            if dx * dx + dy * dy <= r2:
                idx = (y * width + x) * 4
                buf[idx] = r
                buf[idx + 1] = g
                buf[idx + 2] = b
                buf[idx + 3] = a
