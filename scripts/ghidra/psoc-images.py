"""Splits the vendor PSoC .cyacd into flash and configuration images.

Usage: python3 scripts/ghidra/psoc-images.py <out dir> [firmware.cyacd]

Each .cyacd row holds 256 flash bytes and 32 bytes that the PSoC 5LP
keeps in the ECC area when ECC is off. PSoC Creator stores the device
configuration there. Writes:

- flash.bin: flash from 0x10000 to 0x40000, 0xFF where no row exists.
- config.bin: the 32-byte ECC area of every row, row order, from row 0.
"""
import pathlib
import sys

DEFAULT = "/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsemblePSoC.cyacd"
ROW_BYTES = 256
ECC_BYTES = 32
ROWS = 4 * 256
APPLICATION = 0x10000


def main():
    out = pathlib.Path(sys.argv[1])
    lines = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else DEFAULT).read_text().split()
    flash = bytearray(b"\xff" * (ROWS * ROW_BYTES))
    config = bytearray(ROWS * ECC_BYTES)
    for line in lines[1:]:
        row = bytes.fromhex(line[1:])
        index = row[0] * 256 + int.from_bytes(row[1:3], "big")
        data = row[5:5 + int.from_bytes(row[3:5], "big")]
        flash[index * ROW_BYTES:(index + 1) * ROW_BYTES] = data[:ROW_BYTES]
        config[index * ECC_BYTES:(index + 1) * ECC_BYTES] = data[ROW_BYTES:]
    out.mkdir(parents=True, exist_ok=True)
    (out / "flash.bin").write_bytes(flash[APPLICATION:])
    (out / "config.bin").write_bytes(config)


if __name__ == "__main__":
    main()
