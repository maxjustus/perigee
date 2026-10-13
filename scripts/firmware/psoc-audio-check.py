"""Check audio tables and emulate pure gain functions. No device access."""

import argparse
from pathlib import Path
import runpy
import struct

from unicorn import UC_ARCH_ARM, UC_MODE_THUMB, Uc
from unicorn.arm_const import (
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_SP,
)

PROVENANCE = runpy.run_path(str(Path(__file__).parents[1] / "provenance.py"))


def main():
    if not __debug__:
        raise SystemExit("Run without Python optimization to retain verification checks")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flash", nargs="?", default=PROVENANCE["path"]("flash.bin"))
    args = parser.parse_args()
    flash = Path(args.flash).read_bytes()
    source, target, size, _ = struct.unpack_from("<4I", flash, 0x153C4)
    assert (source, target, size) == (0x253D8, 0x1FFF8108, 0xDC8)
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(0x10000, 0x30000)
    cpu.mem_write(0x10000, flash)
    cpu.mem_map(0x1FFF8000, 0x8000)
    cpu.mem_write(target, flash[source - 0x10000 : source - 0x10000 + size])
    tables = [
        (0x1FFF8110, 6),
        (0x1FFF8188, 31),
        (0x1FFF81A8, 21),
        (0x1FFF81C0, 31),
        (0x1FFF81E0, 21),
        (0x1FFF81F8, 31),
        (0x1FFF8218, 21),
        (0x1FFF8230, 31),
        (0x1FFF8250, 21),
        (0x1FFF8268, 21),
        (0x1FFF8280, 15),
        (0x1FFF8290, 10),
        (0x1FFF829C, 17),
        (0x1FFF82B0, 15),
        (0x1FFF82C0, 15),
        (0x1FFF82D0, 16),
        (0x1FFF82FC, 120),
        (0x1FFF8374, 122),
    ]
    for address, length in tables:
        location = source + address - target
        data = bytes(cpu.mem_read(address, length))
        print(f"RAM {address:#010x} flash {location:#07x}: {data.hex(' ')}")
    for gain, expected in [
        (-200, 0),
        (-60.1, 0),
        (-60, 8),
        (-12, 0x800),
        (-6, 0x1000),
        (-3, 0x168C),
        (0, 0x2000),
        (3, 0x2D18),
        (6, 0x4000),
        (12, 0x8000),
    ]:
        low, high = struct.unpack("<II", struct.pack("<d", gain))
        actual = call(cpu, 0x18534, low, high)
        assert actual == expected, (gain, actual, expected)
        print(f"gain {gain:g} dB: {actual:#06x}")
    for pan, expected in [(0, 0), (64, -3), (128, -200)]:
        bits = call(cpu, 0x18470, pan, 0)
        actual = struct.unpack("<f", struct.pack("<I", bits))[0]
        assert actual == expected, (pan, actual, expected)
        print(f"pan {pan}: {actual:g} dB")
    print("PASS: relocation, ten coefficients, three pan values")


def call(cpu, address, low, high):
    cpu.reg_write(UC_ARM_REG_R0, low)
    cpu.reg_write(UC_ARM_REG_R1, high)
    cpu.reg_write(UC_ARM_REG_SP, 0x1FFFF000)
    cpu.reg_write(UC_ARM_REG_LR, 0x10001)
    cpu.emu_start(address | 1, 0x10000, count=1_000_000)
    if cpu.reg_read(UC_ARM_REG_PC) != 0x10000:
        raise RuntimeError(f"Function {address:#x} did not return before the instruction limit")
    return cpu.reg_read(UC_ARM_REG_R0)


if __name__ == "__main__":
    main()
