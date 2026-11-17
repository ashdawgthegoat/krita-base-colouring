"""Offline unit tests for Krita MCP edit_batch payload helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from krita_batch_builder import (  # noqa: E402
    MAX_BATCH_EDITS,
    build_clear_and_refill_batch,
    build_contiguous_fill_batches,
    build_polygon_fill_batch,
    build_seal_gaps_batch,
    union_bboxes,
)


class TestKritaBatchBuilder(unittest.TestCase):
    def test_union_bboxes_clamps_to_arbitrary_canvas(self) -> None:
        rect = union_bboxes([(10, 12, 20, 30), (140, 90, 25, 40)], pad=8, canvas_size=(160, 120))
        self.assertEqual(rect, (2, 4, 158, 116))

    def test_contiguous_fill_batches_chunk_within_limit(self) -> None:
        seeds = [(10 + i, 20) for i in range(125)]
        batches = build_contiguous_fill_batches(
            target_layer="Base_Colours/Shell_Base",
            color="#3a7ca5",
            seeds=seeds,
            fill_bbox=(5, 5, 200, 100),
            grow_px=1,
            document=1,
        )
        self.assertEqual(len(batches), 3)
        for batch in batches:
            self.assertLessEqual(len(batch["edits"]), MAX_BATCH_EDITS)
            self.assertEqual(batch["edits"][0]["arguments"]["combine"], "replace")
            if len(batch["edits"]) > 4:
                self.assertEqual(batch["edits"][1]["arguments"]["combine"], "add")
            self.assertEqual(batch["edits"][-1], {"tool": "set_selection", "arguments": {"mode": "none"}})

    def test_seal_polygon_and_recovery_batches(self) -> None:
        seal = build_seal_gaps_batch([(64, 15, 66, 15), (89, 58, 90, 59)])
        self.assertEqual(seal["edits"][0]["tool"], "draw")
        self.assertEqual(len(seal["edits"][0]["arguments"]["commands"]), 2)

        poly = build_polygon_fill_batch("Base_Colours/Eye_Base", "#4aa4ee", [[[10, 10], [20, 10], [20, 18], [10, 18]]])
        self.assertEqual(poly["edits"][0]["tool"], "select_polygon")
        self.assertEqual(poly["edits"][1]["tool"], "draw")

        rec = build_clear_and_refill_batch(
            wrong_layer="Base_Colours/Outer_Base",
            correct_layer="Base_Colours/Trim_Base",
            color="#20222a",
            seeds=[(80, 60)],
            region_bbox=(70, 50, 25, 25),
        )
        tools = [e["tool"] for e in rec["edits"]]
        self.assertEqual(tools, ["select_content", "draw", "set_selection", "draw", "set_selection"])
        self.assertEqual(rec["edits"][1]["arguments"]["commands"][0]["type"], "clear")
        self.assertEqual(rec["edits"][3]["arguments"]["commands"][0]["type"], "fill_rect")


if __name__ == "__main__":
    unittest.main()
