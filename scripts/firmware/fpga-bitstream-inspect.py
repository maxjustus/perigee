#!/usr/bin/env python3
"""Inspect the gx25f image offline. Never write the input file."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--normalized", type=Path)
    args = parser.parse_args()
    raw = args.image.read_bytes()
    reverse = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
    if len(raw) != 1813864:
        parser.error("Expected the 1,813,864-byte gx25f image")
    data = raw.translate(reverse) if raw[128:132] == b"VVVV" else raw
    if data[128:132] != b"jjjj":
        parser.error("Unknown image header")
    if not data[0x110] & 2:
        parser.error("Compressed images are not supported")

    checks = {
        "oram": [(0x84, 164)],
        "pram": [(564 + i * 460, 460) for i in range(85)],
        "cram": [(39664 + i * 460, 460) for i in range(3856)],
        "postamble": [(1813424, 88), (1813512, 12)],
    }
    result = {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "normalized_sha256": hashlib.sha256(data).hexdigest(),
        "byte_bits_reversed": data != raw,
        "crc16": {},
    }
    for name, frames in checks.items():
        bad = [
            hex(start)
            for start, size in frames
            if crc16(data[start : start + size]) != 0
        ]
        result["crc16"][name] = {"frames": len(frames), "bad_offsets": bad}

    excluded = (318, 1371, 2417, 3166)
    bad_edcrc = []
    deltas = Counter()
    for x in range(3856):
        start = 39664 + 460 * x
        frame = data[start : start + 460]
        stored = int.from_bytes(frame[452:456], "little")
        expected = 0 if any(z <= x < z + 256 for z in excluded) else crc32(frame)
        if stored != expected:
            bad_edcrc.append(x)
            deltas[f"{stored ^ expected:08x}"] += 1
    result["transport_crc16_agreement"] = all(
        not check["bad_offsets"] for check in result["crc16"].values()
    )
    result["mistral_edcrc"] = {
        "frames": 3856,
        "agreement": not bad_edcrc,
        "bad_columns": bad_edcrc,
        "xor_deltas": deltas,
    }
    result["postamble_ff"] = data[1813524:] == b"\xff" * 340
    strips = []
    for strip in range(32):
        value = 0
        for bit in range(40):
            byte = data[0x84 + (strip >> 3) + 4 * bit]
            value |= ((byte >> (7 - (strip & 7))) & 1) << bit
        strips.append(f"{value:010x}")
    result["oram_strips"] = strips
    print(json.dumps(result, indent=2))
    if args.normalized:
        with args.normalized.open("xb") as output:
            output.write(data)


def crc16(data):
    accum = 0xFFFF
    for byte in data:
        accum ^= byte
        for _ in range(8):
            accum = (accum >> 1) ^ (0xA001 if accum & 1 else 0)
    return accum


def crc32(frame):
    accum = 1
    words = [
        int.from_bytes(frame[28 + i * 4 : 32 + i * 4], "little") for i in range(106)
    ]
    for bit in range(31, -1, -1):
        for word in words:
            carry = ((word >> bit) ^ (accum >> 31)) & 1
            accum = ((accum << 1) & 0xFFFFFFFF) ^ (0xF4ACFB13 if carry else 0)
    return accum


if __name__ == "__main__":
    main()
