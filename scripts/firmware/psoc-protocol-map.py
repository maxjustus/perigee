"""Print static PSoC protocol evidence. No device access.

Run with uv run --with capstone scripts/firmware/psoc-protocol-map.py.
Pass hexadecimal start and end addresses to disassemble a range.
"""
import hashlib
from pathlib import Path
import struct
import sys


def main():
    image = Path('/tmp/apogee-fw/flash.bin').read_bytes()
    if len(sys.argv) == 3:
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
        start, end = (int(arg, 16) for arg in sys.argv[1:])
        for insn in Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS).disasm(
            image[start - 0x10000:end - 0x10000], start
        ):
            print(f'{insn.address:08x}: {insn.mnemonic:8} {insn.op_str}')
        return
    print('SHA256', hashlib.sha256(image).hexdigest())
    offset = 0
    saved = []
    for index in range(60):
        address = 0x25EBC + index * 8
        command, size, p1, p2, _, default, volatile = struct.unpack_from(
            '<BBBBHBB', image, address - 0x10000
        )
        length = size * max(p1, 1) * max(p2, 1)
        print(f'{address:05x} {command:02x} {size} {p1} {p2} '
              f'{offset:03x} {default:02x} {volatile}')
        if not volatile & 1:
            saved.append((command, size, p1, p2, length))
        offset += length
    position = 4 + 4 * len(saved)
    print(f'RAM bytes {offset:#x}, saved descriptors {len(saved)}, data start {position:#x}')
    for command, size, p1, p2, length in saved:
        print(f'EEPROM {command:02x} {position:03x}-{position + length - 1:03x}')
        position += length
    print(f'EEPROM end {position:#x}')
    print('Report IDs', ' '.join(f'{image[0x1609c + i * 8]:02x}' for i in range(28)))


if __name__ == '__main__':
    main()
