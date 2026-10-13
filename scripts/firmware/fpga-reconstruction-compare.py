#!/usr/bin/env python3
"""Compare copied gx25f images with raw Mistral cycles. No image writes."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import runpy

CRC = runpy.run_path(str(Path(__file__).with_name("fpga-bitstream-inspect.py")))
NAMES = (
    "E2FPGA.bin",
    "Element2x4_FPGA.bin",
    "Element4x6_FPGA.bin",
    "Element8x8_FPGA.bin",
)
START, FRAME, COLUMNS = 39664, 460, 3856
EXCLUDED = (318, 1371, 2417, 3166)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    geometry = read_geometry(args.source)
    reports = []
    for name in NAMES:
        raw = (args.work / name).read_bytes()
        cycle = (args.work / (name + ".cycle.rbf")).read_bytes()
        reports.append(compare(name, raw, cycle, geometry))
    print(json.dumps(reports, indent=2))


def read_geometry(source):
    die = (source / "libmistral/cvd-gx25f.cc").read_text()
    xmap = list(
        map(int, re.findall(r"\d+", die.split("// x to bit x")[1].split("}")[0]))
    )
    columns = re.findall(r"T_\w+", die.split("// column types")[1].split("}")[0])
    spans = list(
        map(
            int,
            re.findall(
                r"\d+", die.split("gx25f_bel_spans_info[] = {")[1].split("0xff")[0]
            ),
        )
    )
    tiles = []
    while spans:
        first, last, count = spans[:3]
        ranges = spans[3 : 3 + 2 * count]
        spans = spans[3 + 2 * count :]
        for x in range(first, last + 1):
            if columns[x] == "T_MLAB":
                for low, high in zip(ranges[::2], ranges[1::2]):
                    tiles.extend((x, y) for y in range(low, high + 1))
    mux = (source / "data/mlab-mux.txt").read_text().splitlines()
    lut = next(line.split()[3:] for line in mux if line.startswith("i lut_mask "))
    lut = [tuple(map(int, pair.split("."))) for pair in lut]
    disable = next(line.split()[3] for line in mux if line.startswith("g ram_dis "))
    disable = tuple(map(int, disable.split(".")))
    expanded = []
    for i in range(4):
        expanded.extend((x, 85 - 8 * i - y) for x, y in lut)
    expanded.extend((x, 53 if i < 32 else 47) for i, (x, _) in enumerate(lut))
    for i in range(4):
        expanded.extend((x, 8 * i + y) for x, y in lut)
    expanded.extend((x, 32 if i < 32 else 38) for i, (x, _) in enumerate(lut))
    assert len(tiles) == 291 and len(set(expanded)) == 640
    return xmap, tiles, disable, expanded


def compare(name, raw, cycle, geometry):
    assert len(raw) == len(cycle) == 1813864
    reverse = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
    data = raw.translate(reverse)
    assert data[128:132] == b"jjjj"
    blocks, masks = writable_masks(data, geometry)
    _, cycle_masks = writable_masks(cycle, geometry)
    differences = [i for i, (a, b) in enumerate(zip(data, cycle)) if a != b]
    allowed = {
        START + FRAME * x + j
        for x in range(COLUMNS)
        for j in (452, 453, 454, 455, 458, 459)
    }
    groups = defaultdict(list)
    unmasked_bad, masked_bad, force_one_bad = [], [], []
    masked_cycle = bytearray(cycle)
    for x in range(COLUMNS):
        start = START + FRAME * x
        frame = data[start : start + FRAME]
        old = cycle[start : start + FRAME]
        stored = int.from_bytes(frame[452:456], "little")
        excluded = any(base <= x < base + 256 for base in EXCLUDED)
        unmasked = 0 if excluded else CRC["crc32"](frame)
        masked = 0 if excluded else masked_crc32(frame, masks.get(x, set()))
        ones = 0 if excluded else masked_crc32(frame, masks.get(x, set()), 1)
        if stored != unmasked:
            unmasked_bad.append(x)
        if stored != masked:
            masked_bad.append(x)
        if stored != ones:
            force_one_bad.append(x)
        if frame != old:
            delta = stored ^ int.from_bytes(old[452:456], "little")
            transport = int.from_bytes(frame[458:460], "little") ^ int.from_bytes(
                old[458:460], "little"
            )
            groups[(delta, transport)].append(x)
        new_crc = 0 if excluded else masked_crc32(old, cycle_masks.get(x, set()))
        masked_cycle[start + 452 : start + 456] = new_crc.to_bytes(4, "little")
        new_transport = CRC["crc16"](masked_cycle[start : start + 458])
        masked_cycle[start + 458 : start + 460] = new_transport.to_bytes(2, "little")
    transports = [(0x84, 164)] + [(564 + FRAME * i, FRAME) for i in range(85)]
    transports += [(START + FRAME * i, FRAME) for i in range(COLUMNS)]
    transports += [(1813424, 88), (1813512, 12)]
    bad_transport = [
        hex(start)
        for start, size in transports
        if CRC["crc16"](data[start : start + size])
    ]
    set_bits = sum(
        (data[START + FRAME * x + bit // 8] >> (bit % 8)) & 1
        for x, bits in masks.items()
        for bit in bits
    )
    return {
        "name": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "transport_frames": len(transports),
        "bad_transport": bad_transport,
        "ram_tiles": blocks,
        "mask_bits": sum(map(len, masks.values())),
        "mask_bits_set": set_bits,
        "unmasked_bad_columns": unmasked_bad,
        "zero_mask_bad_columns": masked_bad,
        "one_mask_bad_columns": force_one_bad,
        "raw_cycle_different_bytes": len(differences),
        "raw_cycle_different_bits": sum(
            (a ^ b).bit_count() for a, b in zip(data, cycle)
        ),
        "raw_cycle_nonchecksum_offsets": [
            hex(i) for i in differences if i not in allowed
        ],
        "model_cycle_byte_identical": bytes(masked_cycle) == data,
        "groups": [
            {
                "columns": xs,
                "edcrc_xor": f"{delta:08x}",
                "crc16_xor": f"{transport:04x}",
            }
            for (delta, transport), xs in groups.items()
        ],
    }


def writable_masks(data, geometry):
    xmap, tiles, disable, lut = geometry
    blocks, masks = [], defaultdict(set)
    for x, y in tiles:
        base_x, base_y = xmap[x], 2 + 86 * y
        col, bit = base_x + disable[0], wire_bit(base_y + disable[1])
        value = (data[START + FRAME * col + bit // 8] >> (bit % 8)) & 1
        if value:
            continue
        blocks.append([x, y])
        for dx, dy in lut:
            masks[base_x + dx].add(wire_bit(base_y + dy))
    return blocks, masks


def wire_bit(y):
    return 224 + (31 ^ ((y - 20) // 106)) + 32 * ((y - 20) % 106)


def masked_crc32(frame, bits, value=0):
    masked = bytearray(frame)
    for bit in bits:
        if value:
            masked[bit // 8] |= 1 << (bit % 8)
        else:
            masked[bit // 8] &= ~(1 << (bit % 8))
    return CRC["crc32"](masked)


if __name__ == "__main__":
    main()
