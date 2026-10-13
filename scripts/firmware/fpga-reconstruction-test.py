#!/usr/bin/env python3
"""Test the EDCRC hypothesis against four copied vendor images."""

from pathlib import Path
import runpy
import sys
import unittest


class ReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = runpy.run_path(
            str(Path(__file__).with_name("fpga-reconstruction-compare.py"))
        )
        cls.geometry = cls.code["read_geometry"](cls.source)
        cls.fixtures = []
        for name in cls.code["NAMES"]:
            raw = (cls.work / name).read_bytes()
            cycle = (cls.work / (name + ".cycle.rbf")).read_bytes()
            cls.fixtures.append((name, raw, cycle))

    def test_all_four_checksum_models_and_cycles(self):
        for name, raw, cycle in self.fixtures:
            with self.subTest(image=name):
                report = self.code["compare"](name, raw, cycle, self.geometry)
                self.assertEqual(report["bad_transport"], [])
                self.assertEqual(report["transport_frames"], 3944)
                expected = 192 if name == "E2FPGA.bin" else 128
                self.assertEqual(len(report["unmasked_bad_columns"]), expected)
                self.assertEqual(report["raw_cycle_nonchecksum_offsets"], [])
                self.assertEqual(report["zero_mask_bad_columns"], [])
                self.assertEqual(len(report["one_mask_bad_columns"]), expected)
                self.assertTrue(report["model_cycle_byte_identical"])
                self.assertEqual((self.work / name).read_bytes(), raw)
                self.assertEqual(
                    (self.work / (name + ".cycle.rbf")).read_bytes(), cycle
                )

    def test_writable_data_mutation_changes_only_unmasked_crc(self):
        reverse = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
        for name, raw, _ in self.fixtures:
            with self.subTest(image=name):
                data = raw.translate(reverse)
                _, masks = self.code["writable_masks"](data, self.geometry)
                col = min(masks)
                start = self.code["START"] + self.code["FRAME"] * col
                frame = data[start : start + self.code["FRAME"]]
                modified = bytearray(frame)
                bit = min(masks[col])
                modified[bit // 8] ^= 1 << (bit % 8)
                crc = self.code["CRC"]["crc32"]
                self.assertNotEqual(crc(frame), crc(modified))
                masked = self.code["masked_crc32"]
                self.assertEqual(
                    masked(frame, masks[col]), masked(modified, masks[col])
                )
                modified = bytearray(frame)
                bit = next(bit for bit in range(224, 452 * 8) if bit not in masks[col])
                modified[bit // 8] ^= 1 << (bit % 8)
                self.assertNotEqual(
                    masked(frame, masks[col]), masked(modified, masks[col])
                )

    def test_mask_geometry_and_raw_bit_coordinates(self):
        xmap, tiles, disable, lut = self.geometry
        self.assertEqual(len(tiles), 291)
        self.assertEqual(disable, (42, 44))
        self.assertEqual(len(set(lut)), 640)
        self.assertEqual(sorted({x for x, _ in lut}), list(range(7, 39)))
        self.assertEqual(xmap[8] + 7, 757)
        self.assertEqual(xmap[42] + 38, 3501)
        self.assertEqual(self.code["wire_bit"](88 + 79), 1566)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: fpga-reconstruction-test.py WORK MISTRAL_SOURCE")
    ReconstructionTests.work = Path(sys.argv[1]).resolve()
    ReconstructionTests.source = Path(sys.argv[2]).resolve()
    unittest.main(argv=[sys.argv[0]], verbosity=2)
