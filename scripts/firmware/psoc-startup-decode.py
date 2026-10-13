"""Decode Ensemble startup tables without device access.

Usage: python3 scripts/firmware/psoc-startup-decode.py [/tmp/apogee-fw]
The register model covers table writes, not reset values or peripheral effects.
"""

import collections
import hashlib
import json
import pathlib
import re
import runpy
import struct
import sys

PROVENANCE = runpy.run_path(str(pathlib.Path(__file__).parents[1] / "provenance.py"))


def main():
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else PROVENANCE["path"]("flash.bin").parent
    flash = (root / "flash.bin").read_bytes()
    config = (root / "config.bin").read_bytes()
    if len(flash) != 0x30000 or len(config) != 0x8000:
        raise ValueError("Expected 0x30000 flash bytes and 0x8000 configuration bytes")
    header = (root / "cydevice_trm.h").read_text()
    addresses = {
        name: int(value, 16)
        for name, value in re.findall(r"#define (CY\w+) (0x[0-9a-fA-F]+)u", header)
    }
    names = collections.defaultdict(list)
    for name, address in addresses.items():
        if name.startswith("CYREG_"):
            names[address].append(name)
    memory = {}
    writes = []
    zeros = []
    copies = []
    for index in range(10):
        dest, size = struct.unpack_from("<IH", flash, 0x15344 + 6 * index)
        zeros.append([hex(dest), size])
        for offset in range(size):
            memory[dest + offset] = [0, f"zero descriptor {0x25344 + 6 * index:#x}"]
    for index in range(3):
        dest, source, size = struct.unpack_from("<IIH", flash, 0x15380 + 10 * index)
        copies.append([hex(dest), hex(source), size])
        copy(memory, dest, source, size, config)
    cursor = 0x20B0
    groups = []
    for index in range(44):
        (word,) = struct.unpack_from("<I", config, 0x2000 + 4 * index)
        base, count = word & ~255, word & 255
        groups.append([hex(0x48002000 + 4 * index), hex(base), count])
        for _ in range(count):
            offset, value = config[cursor : cursor + 2]
            address = base + offset
            source = f"{0x48000000 + cursor:#x}"
            writes.append([hex(address), value, names[address], source])
            memory[address] = [value, source]
            cursor += 2
    if cursor != 0x30C8:
        raise ValueError(f"Unexpected sparse table end: {cursor:#x}")
    for port, source, size in [
        (0, 0x3248, 8),
        (12, 0x3250, 10),
        (15, 0x325C, 10),
        (1, 0x3268, 10),
        (2, 0x3274, 8),
        (3, 0x327C, 10),
        (4, 0x3288, 8),
        (5, 0x3290, 8),
        (6, 0x3298, 8),
    ]:
        dest = addresses[f"CYREG_PRT{port}_{'DR' if size == 10 else 'DM0'}"]
        copies.append([hex(dest), hex(0x48000000 + source), size])
        copy(memory, dest, 0x48000000 + source, size, config)
    pins = {}
    for port in [0, 1, 2, 3, 4, 5, 6, 12, 15]:
        regs = {}
        for name, address in addresses.items():
            if (
                name.startswith(
                    (f"CYREG_PRT{port}_", f"CYREG_PRTDSI{port}_", f"CYREG_PICU{port}_")
                )
                and address in memory
            ):
                regs[name] = memory[address]
        dm = [memory[addresses[f"CYREG_PRT{port}_DM{i}"]][0] for i in range(3)]
        pins[port] = {
            "drive_modes": [
                sum(((dm[i] >> pin) & 1) << i for i in range(3)) for pin in range(8)
            ],
            "registers": regs,
        }
    print(
        json.dumps(
            {
                "sha256": {
                    "flash.bin": hashlib.sha256(flash).hexdigest(),
                    "config.bin": hashlib.sha256(config).hexdigest(),
                },
                "vectors": [hex(x) for x in struct.unpack_from("<4I", flash)],
                "region": [hex(x) for x in struct.unpack_from("<4I", flash, 0x153C4)],
                "zeros": zeros,
                "copies": copies,
                "groups": groups,
                "sparse_writes": writes,
                "pins": pins,
            },
            indent=2,
        )
    )


def copy(memory, dest, source, size, config):
    offset = source - 0x48000000
    if not 0 <= offset <= len(config) - size:
        raise ValueError(
            f"Configuration source outside image: {source:#x}, size {size}"
        )
    for index in range(size):
        memory[dest + index] = [config[offset + index], hex(source + index)]


if __name__ == "__main__":
    main()
