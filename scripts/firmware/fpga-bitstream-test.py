#!/usr/bin/env python3
"""Run offline inspector tests against a supplied copy of E2FPGA.bin."""

import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

PROVENANCE = runpy.run_path(str(Path(__file__).parents[1] / "provenance.py"))


class InspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.image = Path(cls.scratch.name) / "input.bin"
        cls.image.write_bytes(cls.source.read_bytes())
        cls.raw = cls.image.read_bytes()
        cls.reverse = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
        cls.normalized = cls.raw.translate(cls.reverse)
        cls.script = Path(__file__).with_name("fpga-bitstream-inspect.py")

    def test_orientation_equivalence(self):
        original = self.inspect(self.raw)
        normalized = self.inspect(self.normalized)
        self.assertEqual(original.returncode, 0, original.stderr)
        self.assertEqual(normalized.returncode, 0, normalized.stderr)
        a, b = json.loads(original.stdout), json.loads(normalized.stdout)
        self.assertTrue(a["byte_bits_reversed"])
        self.assertFalse(b["byte_bits_reversed"])
        for key in ["crc16", "mistral_edcrc", "oram_strips", "normalized_sha256"]:
            self.assertEqual(a[key], b[key])
        self.assertTrue(a["transport_crc16_agreement"])
        self.assertFalse(a["mistral_edcrc"]["agreement"])
        self.assertEqual(len(a["mistral_edcrc"]["bad_columns"]), 192)
        self.assertEqual(sum(v["frames"] for v in a["crc16"].values()), 3944)

    def test_deliberate_crc16_corruption(self):
        data = bytearray(self.raw)
        data[0x90] ^= 1
        result = self.inspect(data)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["transport_crc16_agreement"])
        self.assertEqual(report["crc16"]["oram"]["bad_offsets"], ["0x84"])
        for region in ["pram", "cram", "postamble"]:
            self.assertEqual(report["crc16"][region]["bad_offsets"], [])

    def test_malformed_length(self):
        for data in [b"", self.raw[:-1], self.raw + b"\x00"]:
            with self.subTest(length=len(data)):
                result = self.inspect(data)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Expected the 1,813,864-byte", result.stderr)

    def test_malformed_header(self):
        data = bytearray(self.raw)
        data[128] ^= 1
        result = self.inspect(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown image header", result.stderr)

    def test_normalized_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=self.image.parent) as directory:
            output = Path(directory) / "normalized.rbf"
            result = self.inspect(self.raw, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), self.normalized)
            output.write_bytes(b"preserve this file")
            result = self.inspect(self.raw, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FileExistsError", result.stderr)
            self.assertEqual(output.read_bytes(), b"preserve this file")

    def test_refuse_input_as_output(self):
        with tempfile.TemporaryDirectory(dir=self.image.parent) as directory:
            image = Path(directory) / "input.bin"
            image.write_bytes(self.raw)
            result = subprocess.run(
                [
                    sys.executable,
                    str(self.script),
                    str(image),
                    "--normalized",
                    str(image),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(image.read_bytes(), self.raw)

    def inspect(self, data, normalized=None):
        with tempfile.TemporaryDirectory(dir=self.image.parent) as directory:
            image = Path(directory) / "input.bin"
            image.write_bytes(data)
            command = [sys.executable, str(self.script), str(image)]
            if normalized is not None:
                command.extend(["--normalized", str(normalized)])
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(image.read_bytes(), data)
            return result


if __name__ == "__main__":
    default = PROVENANCE["path"]("E2FPGA.bin")
    if len(sys.argv) != 2:
        if not default.exists():
            raise SystemExit("Usage: fpga-bitstream-test.py /path/to/E2FPGA.bin")
        sys.argv.append(str(default))
    InspectorTests.source = Path(sys.argv[1]).resolve()
    unittest.main(argv=[sys.argv[0]], verbosity=2)
