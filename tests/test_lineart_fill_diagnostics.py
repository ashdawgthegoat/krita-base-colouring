"""Offline unit tests for deterministic lineart fill diagnostics."""

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

from generate_fixtures import generate_all  # noqa: E402
from lineart_fill_diagnostics import (  # noqa: E402
    check_seeds,
    find_leak_bottlenecks,
    scan_enclosed_components,
    trace_component,
)
from png_io import read_png_rgba  # noqa: E402


class TestLineartFillDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        generate_all(FIXTURES_DIR)
        cls.broken = read_png_rgba(FIXTURES_DIR / "synthetic_broken_lineart.png")
        cls.sealed = read_png_rgba(FIXTURES_DIR / "synthetic_sealed_lineart.png")

    def test_seed_validation_catches_opaque_ink_and_oob(self) -> None:
        alpha = self.sealed.extract_alpha()
        statuses = check_seeds(alpha, self.sealed.width, self.sealed.height, [(60, 50), (20, 15), (999, 5)])
        self.assertTrue(statuses[0].valid)
        self.assertFalse(statuses[1].valid)
        self.assertEqual(statuses[1].reason, "opaque_ink_pixel")
        self.assertFalse(statuses[2].valid)
        self.assertEqual(statuses[2].reason, "out_of_bounds")

    def test_broken_contour_detects_background_and_neighbor_bottlenecks(self) -> None:
        alpha = self.broken.extract_alpha()
        # Left_Body (60, 50) leaks to background (5, 5) through 3px top gap at x=64..66, y=15..16
        bg_rep = find_leak_bottlenecks(alpha, self.broken.width, self.broken.height, (60, 50), (5, 5))
        self.assertEqual(bg_rep.status, "leaked")
        self.assertEqual(bg_rep.narrowest_span, 3)
        self.assertTrue(any(bp.y in (15, 16) and 64 <= bp.x <= 66 for bp in bg_rep.bottlenecks))

        # Left_Body (60, 50) also leaks to Right_Body (100, 30) through 2px seam gap at x=89..90, y=58..59
        nbr_rep = find_leak_bottlenecks(alpha, self.broken.width, self.broken.height, (60, 50), (100, 30))
        self.assertEqual(nbr_rep.status, "leaked")
        self.assertEqual(nbr_rep.narrowest_span, 2)
        self.assertTrue(any(bp.x in (89, 90) and 58 <= bp.y <= 59 for bp in nbr_rep.bottlenecks))

    def test_sealed_contour_separates_regions_and_discovers_negative_space_and_jewel(self) -> None:
        alpha = self.sealed.extract_alpha()
        self.assertEqual(
            find_leak_bottlenecks(alpha, self.sealed.width, self.sealed.height, (60, 50), (5, 5)).status,
            "separated",
        )
        self.assertEqual(
            find_leak_bottlenecks(alpha, self.sealed.width, self.sealed.height, (60, 50), (100, 30)).status,
            "separated",
        )

        # Component scan finds Left_Body, Right_Body, negative-space cutout, and inner soft jewel
        comps = scan_enclosed_components(alpha, self.sealed.width, self.sealed.height, background_seeds=((5, 5),))
        bboxes = [c.bbox for c in comps]
        self.assertEqual(len(comps), 4)
        self.assertIn((30, 37, 17, 46), bboxes)  # intentional negative space aperture inside Left_Body
        self.assertIn((109, 51, 15, 11), bboxes)  # interior soft eye/jewel excluding AA ring

        jewel = trace_component(alpha, self.sealed.width, self.sealed.height, (115, 56))
        self.assertIsNotNone(jewel)
        assert jewel is not None
        self.assertFalse(jewel.touches_border)
        self.assertEqual(jewel.bbox, (109, 51, 15, 11))


if __name__ == "__main__":
    unittest.main()
