import importlib.util
import struct
import unittest
from pathlib import Path


class ResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "front_panel", Path(__file__).with_name("front-panel-resources.py")
        )
        cls.decoder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.decoder)

    def fixture(self):
        header = bytearray(struct.pack("<4H3I", 0x4642, 3, 6, 2, 36, 44, 0))
        index = struct.pack("<4BI4BI", 1, 2, 1, 0, 0, 2, 1, 1, 2, 4)
        header[16] = self.decoder.crc8(header[:16] + index)
        return bytes(header) + index + bytes.fromhex("f80007e0001fffff")

    def test_crc(self):
        self.assertEqual(self.decoder.crc8(b"123456789"), 0xF4)

    def test_pixels_and_frames(self):
        blob = self.fixture()
        assets = self.decoder.parse(blob)
        self.assertEqual(len(assets), 2)
        self.assertEqual(assets[0], (1, 2, 1, 1, 36))
        self.assertEqual(assets[1], (2, 1, 1, 2, 40))
        image = self.decoder.render(blob, assets[0], 0)
        self.assertEqual(image.size, (2, 1))
        self.assertEqual(
            [image.getpixel((x, 0)) for x in range(2)], [(255, 0, 0), (0, 255, 0)]
        )
        self.assertEqual(
            self.decoder.render(blob, assets[1], 0).getpixel((0, 0)), (0, 0, 255)
        )
        self.assertEqual(
            self.decoder.render(blob, assets[1], 1).getpixel((0, 0)), (255, 255, 255)
        )
        with self.assertRaises(ValueError):
            self.decoder.render(blob, assets[1], 2)

    def test_reject_invalid_header(self):
        blob = self.fixture()
        for offset in (0, 2, 6, 8, 12, 16):
            bad = bytearray(blob)
            bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.decoder.parse(bad)
        for end in (0, 19, 35, 43):
            with self.subTest(end=end), self.assertRaises(ValueError):
                self.decoder.parse(blob[:end])

    def test_reject_invalid_index(self):
        for offset, value in ((20, 3), (21, 0), (23, 2), (24, 1), (31, 0), (32, 5)):
            bad = bytearray(self.fixture())
            bad[offset] = value
            bad[16] = self.decoder.crc8(bad[:16] + bad[20:36])
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.decoder.parse(bad)


if __name__ == "__main__":
    unittest.main()
