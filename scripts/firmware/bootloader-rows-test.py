"""Offline tests for the bootloader scan comparator."""

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


rows = load("bootloader-rows")
inspector = load("image-format-inspect")
RAW = rows.VENDOR.read_bytes()


def scan(config=True):
    image, _ = inspector.parse(RAW)
    flash = [[0] * 256 for _ in range(4)]
    for index, data in image.items():
        array, row = divmod(index, 256)
        flash[array][row] = (-sum(data if config else data[:256])) & 255
    return {
        "identity": [0x69, 0xF0, 0x12, 0x2E, 0, 1, 0x1E, 1],
        "sizes": [[256, 255], [0, 255], [0, 255], [0, 255]],
        "flash": flash,
        "eeprom": [0] * 128,
    }


class CompareTest(unittest.TestCase):
    def test_vendor_rows_with_config_bytes_pass(self):
        result = rows.compare(scan(), RAW)
        self.assertTrue(result["pass"])
        self.assertEqual(result["matched_with_config_bytes"], 355)
        self.assertEqual(result["mismatched_rows"], [])

    def test_vendor_rows_without_config_bytes_pass(self):
        result = rows.compare(scan(config=False), RAW)
        self.assertTrue(result["pass"])
        self.assertEqual(result["matched_without_config_bytes"], 355)

    def test_one_changed_row_fails_and_is_named(self):
        changed = scan()
        changed["flash"][2][5] ^= 0x10
        result = rows.compare(changed, RAW)
        self.assertFalse(result["checks"]["image_rows_match"])
        self.assertEqual(result["mismatched_rows"], [[2, 5]])

    def test_identity_is_checked_and_sizes_are_reported(self):
        changed = scan()
        changed["identity"][0] = 0x2E
        changed["sizes"] = [[0, 1023]] * 4
        result = rows.compare(changed, RAW)
        self.assertFalse(result["checks"]["silicon_id"])
        self.assertFalse(result["pass"])
        self.assertEqual(result["sizes"], [[0, 1023]] * 4)
        self.assertNotIn("loader_fills_array_0", result["checks"])


if __name__ == "__main__":
    unittest.main()
