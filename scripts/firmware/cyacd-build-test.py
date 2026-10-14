"""Offline tests for the strict CYACD builder."""

import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
imported = {}


def load(name):
    if name not in imported:
        spec = importlib.util.spec_from_file_location(
            name, Path(__file__).with_name(f"{name}.py")
        )
        imported[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(imported[name])
    return imported[name]


builder = load("cyacd-build")
inspector = load("image-format-inspect")
VENDOR = Path(
    "/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/"
    "EnsemblePSoC.cyacd"
)


def vendor_parts():
    raw = VENDOR.read_bytes()
    report = inspector.inspect(raw)
    rows, _ = inspector.parse(raw)
    flash = b"".join(rows[256 + i][:256] for i in range(report["metadata"]["length"] // 256))
    config = b"".join(rows[256 + i][256:] for i in range(report["metadata"]["length"] // 256))
    metadata = report["metadata"]
    return raw, report, flash, config, metadata


class RoundTripTest(unittest.TestCase):
    def test_rebuild_from_parsed_parts_is_byte_identical(self):
        raw, report, flash, config, metadata = vendor_parts()
        built = builder.build(flash, config, metadata["entry_point"], metadata["length"])
        self.assertEqual(built, raw)

    def test_rebuilt_file_passes_the_inspector(self):
        _, report, flash, config, metadata = vendor_parts()
        built = builder.build(flash, config, metadata["entry_point"], metadata["length"])
        result = inspector.inspect(built)
        self.assertEqual(result["sha256"], report["sha256"])


class AuthoringTest(unittest.TestCase):
    def test_modified_flash_gets_a_fresh_valid_checksum(self):
        _, _, flash, config, metadata = vendor_parts()
        modified = bytearray(flash)
        modified[0x100] ^= 1
        built = builder.build(bytes(modified), config, metadata["entry_point"], metadata["length"])
        result = inspector.inspect(built)
        flash_sum = sum(modified) & 255
        config_sum = sum(config) & 255
        self.assertEqual(result["app_checksum"], (-(flash_sum + config_sum)) & 255)
        self.assertNotEqual(result["app_checksum"], metadata["checksum"])

    def test_modified_config_gets_a_fresh_valid_checksum(self):
        _, _, flash, config, metadata = vendor_parts()
        modified = bytearray(config)
        modified[7] ^= 1
        built = builder.build(flash, bytes(modified), metadata["entry_point"], metadata["length"])
        result = inspector.inspect(built)
        flash_sum = sum(flash) & 255
        config_sum = sum(modified) & 255
        self.assertEqual(result["app_checksum"], (-(flash_sum + config_sum)) & 255)


class RejectionTest(unittest.TestCase):
    def test_rejects_lengths_and_entry_out_of_contract(self):
        _, _, flash, config, metadata = vendor_parts()
        for bad in (b"", flash + b"\x00", b"\xff" * 0x30000):
            with self.subTest(length=len(bad)):
                with self.assertRaisesRegex(ValueError, "length|config"):
                    builder.build(bad, config, metadata["entry_point"], None)
        self.assertRaisesRegex(ValueError, "length", builder.build,
                                b"\x00" * 257, b"\x00" * 64, 0x10011, 257)
        self.assertRaisesRegex(ValueError, "config", builder.build,
                                flash, b"\x00" * 32, 0x10011, metadata["length"])

    def test_rejects_entry_point_outside_the_application(self):
        _, _, flash, config, _ = vendor_parts()
        for entry in (0x10010, 0x0FFF, 0x26201):
            with self.subTest(entry=hex(entry)):
                with self.assertRaisesRegex(ValueError, "entry"):
                    builder.build(flash, config, entry, len(flash))

    def test_rejects_non_default_bootloader_boundary(self):
        _, _, flash, config, metadata = vendor_parts()
        with self.assertRaisesRegex(ValueError, "boundary"):
            builder.build(flash, config, metadata["entry_point"], metadata["length"],
                          bootloader_last_row=254)


if __name__ == "__main__":
    unittest.main()
