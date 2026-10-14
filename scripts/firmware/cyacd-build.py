"""Build a CYACD image from flash, configuration, and metadata parts.

Usage:
    python3 scripts/firmware/cyacd-build.py <flash.bin> <config.bin> \\
        <entry hex> [length hex] > image.cyacd

The builder emits exactly the profile that scripts/firmware/image-format-inspect.py
accepts: one application from 0x10000, 288-byte rows, a 64 KB bootloader
boundary, and one metadata row at 0x3FFC0. Success proves correct
serialization and checksums only, never firmware behavior.
"""

import sys
from pathlib import Path

HEADER = b"2E12F0690000"
APPLICATION = 0x10000
METADATA_ROW = 0x3FFC0
ROW_BYTES = 256
ECC_BYTES = 32


def build(flash, config, entry, length=None, *, bootloader_last_row=255,
          run_type=0, active=0, verified=0, bootloader_version=0,
          app_id=0, app_version=0, customer_id=0):
    if length is None:
        length = len(flash)
    if not 0 < length <= 0x2FF00 or length % ROW_BYTES:
        raise ValueError(f"unsupported application length: {length:#x}")
    rows = length // ROW_BYTES
    if rows > 256 + 255 or len(config) != rows * ECC_BYTES:
        raise ValueError("configuration size does not match the application rows")
    if bootloader_last_row != 255:
        raise ValueError("unsupported bootloader boundary")
    if not entry & 1 or not APPLICATION <= (entry & ~1) < APPLICATION + length:
        raise ValueError(f"entry point is outside the application: {entry:#x}")

    body = bytearray(64)
    body[1:5] = (entry & 0xFFFFFFFF).to_bytes(4, "little")
    body[5:7] = bootloader_last_row.to_bytes(2, "little")
    body[9:13] = length.to_bytes(4, "little")
    body[13] = run_type
    body[16] = active
    body[17] = verified
    body[18:20] = bootloader_version.to_bytes(2, "little")
    body[20:22] = app_id.to_bytes(2, "little")
    body[22:24] = app_version.to_bytes(2, "little")
    body[24:28] = customer_id.to_bytes(4, "little")
    body[0] = row_checksum(flash, config)
    return HEADER + b"\n" + b"\n".join(
        record((256 + i) // 256, (256 + i) % 256,
               flash[i * ROW_BYTES:(i + 1) * ROW_BYTES] + config[i * ECC_BYTES:(i + 1) * ECC_BYTES])
        for i in range(rows)
    ) + b"\n" + record(3, 255, bytes(192) + bytes(body) + bytes(ECC_BYTES)) + b"\n"


def row_checksum(flash, config):
    return (-(sum(flash) + sum(config))) & 0xFF


def record(array, row, data):
    body = bytes([array]) + row.to_bytes(2, "big") + len(data).to_bytes(2, "big") + data
    return b":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper().encode()


def main():
    if len(sys.argv) not in (4, 5):
        raise SystemExit(__doc__)
    flash = Path(sys.argv[1]).read_bytes()
    config = Path(sys.argv[2]).read_bytes()
    entry = int(sys.argv[3], 16)
    length = int(sys.argv[4], 16) if len(sys.argv) == 5 else None
    sys.stdout.buffer.write(build(flash, config, entry, length))


if __name__ == "__main__":
    main()
