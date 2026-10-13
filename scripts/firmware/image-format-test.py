"""Offline tests for the Ensemble CYACD inspection profile."""

import importlib.util
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("image-format-inspect.py")
spec = importlib.util.spec_from_file_location("image_format", SCRIPT)
image_format = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_format)
PROVENANCE = runpy.run_path(str(Path(__file__).parents[1] / "provenance.py"))
VENDOR = PROVENANCE["path"]("EnsemblePSoC.cyacd")
FLASH = PROVENANCE["path"]("flash.bin")
CONFIG = PROVENANCE["path"]("config.bin")


class ImageFormatTests(unittest.TestCase):
    def setUp(self):
        app = bytearray(288)
        app[:8] = bytes.fromhex("0080ff1f11000100")
        app[256] = 7
        metadata = bytearray(288)
        metadata[192] = (-sum(app)) & 255
        metadata[193:197] = (0x10011).to_bytes(4, "little")
        metadata[197:199] = (255).to_bytes(2, "little")
        metadata[201:205] = (256).to_bytes(4, "little")
        self.lines = [b"2E12F0690000", record(1, 0, app), record(3, 255, metadata)]

    def inspect(self, lines=None):
        return image_format.inspect(b"\n".join(self.lines if lines is None else lines) + b"\n")

    def test_small_profile(self):
        result = self.inspect()
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["app_start"], 0x10000)
        self.assertEqual(result["app_end_exclusive"], 0x10100)
        self.assertEqual(result["flash_sum8"], 0xB0)
        self.assertEqual(result["config_sum8"], 7)
        self.assertEqual(result["app_checksum"], 0x49)
        self.assertEqual(result["metadata"]["entry_point"], 0x10011)
        self.assertEqual(result["metadata"]["bootloader_last_row"], 255)
        self.assertIn("not proof", result["limitation"])

    def test_line_endings_and_hex_case(self):
        expected = self.inspect()
        for data in (b"\r\n".join(self.lines), b"\n".join(self.lines).lower()):
            result = image_format.inspect(data)
            self.assertEqual(result["app_checksum"], expected["app_checksum"])

    def test_invalid_text(self):
        for data in (b"", b"\xff", b"\n".join(self.lines) + b"\n\n",
                     b"\n".join(self.lines).replace(b":", b" ", 1),
                     b"\n".join(self.lines).replace(b":01", b":0G", 1),
                     b"\n".join(self.lines).replace(b":01", b":0 1", 1),
                     b"\n".join(self.lines).replace(b":01", b":1", 1)):
            with self.subTest(data=data[:20]), self.assertRaises(ValueError):
                image_format.inspect(data)

    def test_unsupported_header(self):
        for header in (b"2E12F06900", b"2E12F069000000", b"2E12F0680000",
                       b"2E12F0690100", b"2E12F0690001"):
            with self.subTest(header=header), self.assertRaises(ValueError):
                self.inspect([header, *self.lines[1:]])

    def test_bad_row_checksum(self):
        self.lines[1] = self.lines[1][:-2] + b"00"
        with self.assertRaisesRegex(ValueError, "row checksum"):
            self.inspect()

    def test_length_truncation_and_extra_bytes(self):
        original = self.lines[1]
        for line in (original[:-2], original + b"00", b":010000011F" + original[11:]):
            with self.subTest(line=line[:12]), self.assertRaises(ValueError):
                self.inspect([self.lines[0], line, self.lines[2]])

    def test_duplicate_and_out_of_order(self):
        for lines in ([*self.lines, self.lines[1]], [self.lines[0], *reversed(self.lines[1:])]):
            with self.assertRaisesRegex(ValueError, "order|duplicate"):
                self.inspect(lines)

    def test_unsupported_geometry(self):
        for array, row, size in ((0, 0, 288), (4, 0, 288), (64, 0, 288),
                                 (1, 256, 288), (1, 0, 256), (1, 0, 0)):
            with self.subTest(array=array, row=row, size=size), self.assertRaises(ValueError):
                self.inspect([self.lines[0], record(array, row, bytes(size)), self.lines[2]])

    def test_missing_and_extra_rows(self):
        cases = [self.lines[:2], [self.lines[0], self.lines[2]],
                 [*self.lines[:2], record(1, 2, bytes(288)), self.lines[2]]]
        for lines in cases:
            with self.assertRaisesRegex(ValueError, "coverage|metadata"):
                self.inspect(lines)

    def test_metadata_bounds(self):
        for offset, value in ((197, b"\xfe\x00"), (201, bytes(4)),
                              (201, (257).to_bytes(4, "little")),
                              (201, (0x30000).to_bytes(4, "little")),
                              (193, (0x10010).to_bytes(4, "little")),
                              (193, (0x30001).to_bytes(4, "little")),
                              (193, (0x10021).to_bytes(4, "little"))):
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                self.inspect(replace_data(self.lines, 2, offset, value))

    def test_flash_and_config_corruption_after_row_checksum_repair(self):
        for offset in (16, 255, 256, 287):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "application checksum"):
                self.inspect(replace_data(self.lines, 1, offset, b"\x01"))

    def test_metadata_checksum_corruption(self):
        with self.assertRaisesRegex(ValueError, "application checksum"):
            self.inspect(replace_data(self.lines, 2, 192, b"\x00"))

    def test_metadata_flags_are_not_an_app_checksum(self):
        result = self.inspect(replace_data(self.lines, 2, 209, b"\x01"))
        self.assertEqual(result["metadata"]["verified"], 1)
        self.assertEqual(result["app_checksum"], 0x49)

    def test_balanced_corruption_is_not_detected(self):
        lines = replace_data(self.lines, 1, 16, b"\x01\xff")
        self.assertEqual(self.inspect(lines)["app_checksum"], self.inspect()["app_checksum"])

    @unittest.skipUnless(VENDOR.exists(), "vendor CYACD absent")
    def test_vendor_file(self):
        result = image_format.inspect(VENDOR.read_bytes())
        self.assertEqual(result["sha256"], PROVENANCE["sha256"]("EnsemblePSoC.cyacd"))
        self.assertEqual(result["row_count"], 355)
        self.assertEqual(result["arrays"], {"1": [0, 255, 256], "2": [0, 97, 98], "3": [255, 255, 1]})
        self.assertEqual(result["app_end_exclusive"], 0x26200)
        self.assertEqual(result["flash_sum8"], 0x2A)
        self.assertEqual(result["config_sum8"], 0x63)
        self.assertEqual(result["app_checksum"], 0x73)
        self.assertEqual(result["metadata_file_offset"], 0x33174)
        self.assertEqual(result["metadata"]["length"], 0x16200)

    @unittest.skipUnless(VENDOR.exists(), "vendor CYACD absent")
    def test_vendor_corruption_after_row_checksum_repair(self):
        lines = VENDOR.read_bytes().splitlines()
        for index, offset in ((1, 16), (1, 256), (354, 255), (354, 287)):
            body = bytes.fromhex(lines[index][1:].decode())
            value = bytes([body[5 + offset] ^ 1])
            with self.subTest(index=index, offset=offset), self.assertRaisesRegex(ValueError, "application checksum"):
                self.inspect(replace_data(lines, index, offset, value))

    @unittest.skipUnless(VENDOR.exists(), "vendor CYACD absent")
    def test_vendor_internal_hole(self):
        lines = VENDOR.read_bytes().splitlines()
        del lines[100]
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.inspect(lines)

    @unittest.skipUnless(VENDOR.exists() and CONFIG.exists() and FLASH.exists(), "derived baseline absent")
    def test_derived_baseline_includes_synthetic_holes(self):
        flash = bytearray(b"\xff" * 0x30000)
        config = bytearray(0x8000)
        for line in VENDOR.read_bytes().splitlines()[1:]:
            body = bytes.fromhex(line[1:].decode())
            index = body[0] * 256 + int.from_bytes(body[1:3], "big")
            flash[(index - 256) * 256:(index - 255) * 256] = body[5:261]
            config[index * 32:(index + 1) * 32] = body[261:-1]
        self.assertEqual(bytes(flash), FLASH.read_bytes())
        self.assertEqual(bytes(config), CONFIG.read_bytes())
        self.assertEqual(flash[0x16200:0x2FF00], b"\xff" * 0x19D00)
        self.assertEqual(config[:0x2000], bytes(0x2000))

    @unittest.skipUnless(VENDOR.exists(), "vendor CYACD absent")
    def test_cli(self):
        process = subprocess.run([sys.executable, str(SCRIPT), str(VENDOR)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["app_checksum"], 0x73)

    def test_cli_missing_file(self):
        process = subprocess.run([sys.executable, str(SCRIPT), "/nonexistent/image.cyacd"], capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertIn("error:", process.stderr)
        self.assertNotIn("Traceback", process.stderr)


def record(array, row, data):
    body = bytes([array]) + row.to_bytes(2, "big") + len(data).to_bytes(2, "big") + data
    return b":" + (body + bytes([(-sum(body)) & 255])).hex().upper().encode()


def replace_data(lines, index, offset, value):
    body = bytes.fromhex(lines[index][1:].decode())
    data = bytearray(body[5:-1])
    data[offset:offset + len(value)] = value
    result = list(lines)
    result[index] = record(body[0], int.from_bytes(body[1:3], "big"), data)
    return result


if __name__ == "__main__":
    unittest.main()
