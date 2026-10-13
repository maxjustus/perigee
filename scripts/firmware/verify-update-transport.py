#!/usr/bin/env python3
import hashlib
from pathlib import Path
import struct
import unittest


class TransportEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hal = read_slice(
            "/Library/Audio/Plug-Ins/HAL-disabled/ApogeeElementEnsemble.driver/"
            "Contents/MacOS/ApogeeElementEnsemble",
            0x100000C,
        )
        cls.kext = read_slice(
            "/Library/Extensions/ApogeeElementEnsemble.kext/"
            "Contents/MacOS/ApogeeElementEnsemble",
            0x1000007,
        )
        resources = Path(
            "/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources"
        )
        cls.cyacd = (resources / "EnsemblePSoC.cyacd").read_bytes()

    def test_source_hashes(self):
        for data, expected in (
            (
                self.hal,
                "f6c057b0bbda413c111b3cd9ee92c327a410736dc8fef21252cd8e1a8559f4c1",
            ),
            (
                self.kext,
                "4e6c613a454ce9c6b337b3647677d06300757c452c92b408f9d5d97a29ea7b01",
            ),
            (
                self.cyacd,
                "7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24",
            ),
        ):
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)

    def test_transport_selectors(self):
        for address, expected in (
            (0x1484, "22 1c 00 12 01 0c 80 52 22 8d 00 14"),
            (0x1490, "22 1c 00 12 21 0c 80 52 23 00 80 52 8f 8e 00 14"),
            (0x14A0, "e4 03 01 aa 42 1c 00 12 41 0c 80 52 e3 03 02 aa"),
            (0x1578, "e3 03 02 aa e2 03 01 aa 21 00 80 52 cb 8a 00 14"),
            (0x15C8, "41 00 80 52 b9 8a 00 94"),
            (0x87F6C, "21 00 80 52 45 e5 fd 97"),
            (0x880C4, "41 00 80 52 ef e4 fd 97"),
        ):
            expected = bytes.fromhex(expected)
            self.assertEqual(self.hal[address : address + len(expected)], expected)

    def test_bootloader_response_read_sets(self):
        for start, end, buffer, expected in (
            (0x882E0, 0x88314, 0, [1, 0, 2, 3]),
            (0x88384, 0x88390, 0, [14]),
            (0x88694, 0x886CC, 0x20, [1, 2, 3, 0, 6]),
            (0x887E0, 0x88818, 0x20, [1, 2, 3, 0, 6]),
            (0x88980, 0x889DC, 0x10, [1, 0, 2, 3, 7, 4]),
            (0x88B68, 0x88BC8, 0, [1, 0, 2, 3, 10, 5, 4, 7, 6]),
        ):
            offsets = []
            for address in range(start, end, 4):
                word = struct.unpack_from("<I", self.hal, address)[0]
                if word & 0xFFC003E0 == 0x394003E0:
                    offsets.append(((word >> 10) & 4095) - buffer)
            self.assertEqual(offsets, expected)

    def test_kext_success_path(self):
        for address, expected in (
            (0x3DA9, "e8 e0 04 00 00 e9 03 02 00 00"),
            (0x3DC0, "e8 3d 05 00 00 e9 ec 01 00 00"),
            (0x3FB6, "45 31 f6 eb 56"),
            (0x4011, "44 89 f0"),
            (0x42C6, "e8 d5 1c 00 00 44 01 e3"),
            (0x4383, "e9 18 1c 00 00"),
            (0x6070, "31 c0 5b 41 5c 41 5e 41 5f 5d e9 00 00 00 00"),
        ):
            expected = bytes.fromhex(expected)
            self.assertEqual(self.kext[address : address + len(expected)], expected)
        for request, expected in ((1, 0x3DA0), (2, 0x3DB3)):
            offset = struct.unpack_from("<i", self.kext, 0x406C + request * 4)[0]
            self.assertEqual(0x406C + offset, expected)

    def test_external_completion_dispatch(self):
        offset = struct.unpack_from("<H", self.hal, 0xC9C42)[0]
        self.assertEqual(0x81740 + 4 * offset, 0x81D80)
        offset = struct.unpack_from("<H", self.hal, 0xC9C50)[0]
        self.assertEqual(0x819AC + 4 * offset, 0x81EAC)
        self.assertEqual(
            self.hal[0x81E64:0x81E74],
            bytes.fromhex("1f 01 00 71 48 00 80 52 08 05 88 1a 1a 00 00 14"),
        )
        self.assertEqual(self.hal[0x81ED8:0x81EDC], bytes.fromhex("68 9a 04 b9"))

    def test_crc_type_one_loop(self):
        self.assertEqual(
            self.hal[0x88C3C:0x88C74],
            bytes.fromhex(
                "0a 00 80 d2 0b 68 6a 38 0c 01 00 12 6b 01 00 12 "
                "08 3d 01 53 0d 01 09 4a 9f 01 0b 6b 08 01 8d 1a "
                "4a 05 00 91 5f 21 00 71 e1 fe ff 54 00 20 00 91 "
                "21 04 00 f1 61 fe ff 54"
            ),
        )
        self.assertEqual(
            self.hal[0x88658:0x88660], bytes.fromhex("21 0f 80 52 6a 01 00 94")
        )

    def test_bundle_header_and_rows(self):
        lines = self.cyacd.splitlines()
        self.assertEqual(lines[0], b"2E12F0690000")
        self.assertEqual(len(lines) - 1, 355)
        for line in lines[1:]:
            self.assertEqual(line[:1], b":")
            row = bytes.fromhex(line[1:].decode("ascii"))
            self.assertEqual(int.from_bytes(row[3:5], "big"), 288)
            self.assertEqual(len(row), 294)
            self.assertEqual(sum(row) & 255, 0)

    def test_device_completion_crc_bytes(self):
        flash = bytearray(b"\xff" * 0x40000)
        for line in self.cyacd.splitlines()[1:]:
            row = bytes.fromhex(line[1:].decode("ascii"))
            address = row[0] * 0x10000 + int.from_bytes(row[1:3], "big") * 256
            flash[address : address + 256] = row[5:261]
        self.assertEqual(flash[0x182AE:0x182B4], bytes.fromhex("61 23 87 f8 78 30"))
        self.assertEqual(
            flash[0x182CA:0x182D2], bytes.fromhex("97 f8 e3 30 87 f8 7c 30")
        )
        self.assertEqual(flash[0x18288:0x1828C], bytes.fromhex("09 f0 30 fb"))


def read_slice(path, cpu):
    data = Path(path).read_bytes()
    if data[:4] != bytes.fromhex("ca fe ba be"):
        raise ValueError("Expected a FAT32 Mach-O file")
    count = struct.unpack_from(">I", data, 4)[0]
    for index in range(count):
        kind, _, offset, size, _ = struct.unpack_from(">IIIII", data, 8 + 20 * index)
        if kind == cpu:
            return data[offset : offset + size]
    raise ValueError(f"CPU type {cpu:#x} is absent")


if __name__ == "__main__":
    unittest.main()
