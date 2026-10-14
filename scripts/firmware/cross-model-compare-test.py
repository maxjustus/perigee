"""Offline tests for the cross-model firmware comparison."""

import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load("cross-model-compare")
RESOURCES = Path(
    "/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources"
)


def synth(header, rows):
    lines = [header]
    for index, payload in sorted(rows.items()):
        body = (index // 256).to_bytes(1, "big") + (index % 256).to_bytes(2, "big") \
            + len(payload).to_bytes(2, "big") + payload
        lines.append((":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper()).encode())
    return b"\n".join(lines) + b"\n"


class ParseTest(unittest.TestCase):
    def test_parse_and_flash_round_trip(self):
        rows = {256: bytes(range(256)) + bytes(32), 1023: bytes(288)}
        raw = synth(b"2E12F0690000", rows)
        header, parsed = tool.parse(raw)
        self.assertEqual(header, "2E12F0690000")
        self.assertEqual(parsed, rows)
        flash = tool.flash_image(parsed, 0x10000, 0x40000)
        self.assertEqual(flash[0:256], bytes(range(256)))
        self.assertEqual(flash[0x100:0x200], b"\xff" * 0x100)  # absent row
        self.assertEqual(flash[0x2FF00:0x30000], b"\x00" * 0x100)  # metadata row

    def test_row_diff_classifies_overlap_only(self):
        base = {256 + i: bytes([i]) * 288 for i in range(4)}
        other = dict(base)
        other[257] = bytes([2, 2]) + bytes([0]) * 286
        report = tool.row_diff(base, other)
        self.assertEqual(report["identical"], [256, 258, 259])
        self.assertEqual(report["changed"], [257])
        self.assertEqual(report["ensemble_only"], [])
        self.assertEqual(report["element_only"], [])

    def test_row_diff_reports_disjoint_ranges(self):
        report = tool.row_diff({256: bytes(288)}, {257: bytes(288)})
        self.assertEqual(report["ensemble_only"], [256])
        self.assertEqual(report["element_only"], [257])

    def test_function_report_slices_exact_ranges(self):
        flash_a = bytearray(b"\xff" * 0x1000)
        flash_b = bytearray(b"\xff" * 0x1000)
        flash_b[0x12] = flash_a[0x12] ^ 1
        functions = [(0x10, 8, "one"), (0x100, 8, "two")]
        report = tool.function_report(flash_a, flash_b, 0, functions)
        self.assertEqual(report["identical"], [("two", 0x100)])
        self.assertEqual(report["changed"], [("one", 0x10)])
        self.assertEqual(report["uncovered_changed_bytes"], 0)


class VendorTest(unittest.TestCase):
    def setUp(self):
        self.ensemble = tool.parse((RESOURCES / "EnsemblePSoC.cyacd").read_bytes())
        self.element = tool.parse((RESOURCES / "Element.cyacd").read_bytes())

    def test_both_images_are_internally_consistent(self):
        for (header, rows) in (self.ensemble, self.element):
            self.assertEqual(header, "2E12F0690000")
            self.assertIn(1023, rows)
            self.assertEqual(rows[1023][197:199], b"\xff\x00")
        self.assertEqual(len(self.ensemble[1]), 355)
        self.assertEqual(len(self.element[1]), 189)
        self.assertEqual(
            int.from_bytes(self.ensemble[1][1023][201:205], "little"), 0x16200
        )
        self.assertEqual(
            int.from_bytes(self.element[1][1023][201:205], "little"), 0xBC00
        )

    def test_cross_model_report_is_self_consistent(self):
        report, _ = tool.compare(self.ensemble, self.element)
        overlap = report["row_overlap"]
        self.assertEqual(
            overlap["identical_count"] + overlap["changed_count"],
            overlap["overlap_count"],
        )
        self.assertGreater(overlap["changed_count"], 0)
        total = (
            report["functions"]["identical_count"]
            + report["functions"]["changed_count"]
        )
        self.assertEqual(total, report["function_total"])


if __name__ == "__main__":
    unittest.main()
