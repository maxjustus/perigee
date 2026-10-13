"""Offline tests for the read-only device report client."""

from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
import importlib.util
SCRIPT = Path(__file__).with_name("device-reports.py")
spec = importlib.util.spec_from_file_location("device_reports", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class GetWordsTest(unittest.TestCase):
    def test_get_encodes_type_three_with_selector(self):
        self.assertEqual(tool.get_words(0x40, 1), [1, 0, 3 | 0x40 << 8 | 1 << 16])
        self.assertEqual(tool.get_words(0xD5), [1, 0, 0x0000D503])

    def test_get_rejects_commands_outside_the_allowlist(self):
        with self.assertRaisesRegex(ValueError, "allowlist"):
            tool.get_words(0x00)


class DecodeTest(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(tool.decode_versions({"p1": 0, "data": [1, 5, 3]}), "1.5.3")
        self.assertEqual(tool.decode_versions({"p1": 1, "data": [0, 0x56, 0]}), "0.56.0")

    def test_resource_crc_verdict(self):
        match = {"p1": 3, "data": [0, 6, 0x1B]}
        mismatch = {"p1": 3, "data": [0, 6, 0x1C]}
        short = {"p1": 3, "data": [0, 6]}
        self.assertEqual(tool.decode_resource(match), {"version": 6, "crc8": 0x1B, "matches_vendor": True})
        self.assertEqual(tool.decode_resource(mismatch)["matches_vendor"], False)
        self.assertIsNone(tool.decode_resource(short))


class PlanTest(unittest.TestCase):
    def test_dry_run_lists_queries_without_a_socket(self):
        plan = tool.plan()
        self.assertEqual(len(plan["queries"]), 9)
        self.assertTrue(all(q["words"][0:2] == [1, 0] for q in plan["queries"]))
        self.assertIn((0x40, 3), [(q["command"], q["p1"]) for q in plan["queries"]])


if __name__ == "__main__":
    unittest.main()
