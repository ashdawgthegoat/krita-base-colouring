"""Offline unit tests for post-fill transparency, unfilled-pocket, and layer-overlap audits."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))

from base_colour_audit import (  # noqa: E402
    audit_layer_disjointness,
    audit_transparent_cutout,
    find_unfilled_enclosed_islands,
)
from generate_fixtures import generate_all  # noqa: E402
from png_io import PngImage, read_png_rgba  # noqa: E402


class TestBaseColourAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        generate_all(FIXTURES_DIR)
        cls.cutout = read_png_rgba(FIXTURES_DIR / "synthetic_clean_cutout.png")
        cls.comp_hole = read_png_rgba(FIXTURES_DIR / "synthetic_composite_with_hole.png")
        cls.leaked = read_png_rgba(FIXTURES_DIR / "synthetic_leaked_cutout.png")

    def test_clean_cutout_passes_and_preserves_negative_space(self) -> None:
        audit = audit_transparent_cutout(
            self.cutout,
            expected_empty_points=((5, 5), (38, 60)),  # bg corner + internal cutout aperture
            exterior_margin_bbox=(20, 15, 140, 105),
        )
        self.assertTrue(audit.passed)
        self.assertEqual(audit.contaminated_empty_points, 0)
        self.assertEqual(audit.exterior_nonzero_alpha_pixels, 0)

        # Even though Left_Body is pure #FFFFFF, supplying transparent cutout reports ZERO unfilled holes!
        islands = find_unfilled_enclosed_islands(
            self.comp_hole,  # composite image ignored for Left_Body when transparent_img supplied
            background_seeds=((5, 5),),
            negative_space_seeds=((38, 60),),
            transparent_img=self.cutout,
        )
        self.assertEqual(islands, [])

    def test_detects_leaked_background_and_unfilled_hole(self) -> None:
        bad_audit = audit_transparent_cutout(
            self.leaked,
            expected_empty_points=((5, 5), (38, 60)),
            exterior_margin_bbox=(20, 15, 140, 105),
        )
        self.assertFalse(bad_audit.passed)
        self.assertEqual(bad_audit.contaminated_empty_points, 1)
        self.assertGreater(bad_audit.exterior_nonzero_alpha_pixels, 100)

        # Composite check without transparent cutout catches the 6x6 unfilled hole at (110..115, 80..85),
        # alongside #FFFFFF Left_Body if white_lum_threshold mode is used directly
        islands = find_unfilled_enclosed_islands(
            self.comp_hole,
            background_seeds=((5, 5),),
            negative_space_seeds=((38, 60),),
            roi_bbox=(92, 18, 136, 102),
            min_pixels=6,
        )
        self.assertEqual(len(islands), 1)
        self.assertEqual(islands[0].pixel_count, 36)
        self.assertEqual(islands[0].bbox, (110, 80, 6, 6))

    def test_audit_layer_disjointness_detects_sibling_contamination(self) -> None:
        w, h = 40, 40
        buf_a = bytearray(w * h * 4)
        buf_b = bytearray(w * h * 4)
        for y in range(5, 20):
            for x in range(5, 20):
                buf_a[(y * w + x) * 4 + 3] = 255
        for y in range(15, 30):
            for x in range(15, 30):
                buf_b[(y * w + x) * 4 + 3] = 255
        overlaps = audit_layer_disjointness(
            {"MatA_Base": PngImage(w, h, buf_a), "MatB_Base": PngImage(w, h, buf_b)},
            alpha_threshold=200,
        )
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0].overlap_pixels, 25)
        self.assertEqual(overlaps[0].sample_coord, (15, 15))


if __name__ == "__main__":
    unittest.main()
