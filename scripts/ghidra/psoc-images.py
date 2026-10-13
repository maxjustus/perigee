"""Splits the vendor PSoC .cyacd into flash and configuration images.

Usage: python3 scripts/ghidra/psoc-images.py <out dir> [firmware.cyacd]

Each .cyacd row holds 256 flash bytes and 32 bytes that the PSoC 5LP
keeps in the ECC area when ECC is off. PSoC Creator stores the device
configuration there. Writes:

- flash.bin: flash from 0x10000 to 0x40000, 0xFF where no row exists.
- config.bin: the 32-byte ECC area of every row, row order, from row 0.
"""
import pathlib
import runpy
import sys

PROVENANCE = runpy.run_path(str(pathlib.Path(__file__).parents[1] / "provenance.py"))
DEFAULT = PROVENANCE["path"]("EnsemblePSoC.cyacd")
ROW_BYTES = 256
ECC_BYTES = 32
ROWS = 4 * 256
APPLICATION = 0x10000
INSPECT = pathlib.Path(__file__).parents[1] / "firmware" / "image-format-inspect.py"


def main():
    out = pathlib.Path(sys.argv[1])
    flash, config = images(pathlib.Path(sys.argv[2]).read_bytes() if len(sys.argv) > 2 else DEFAULT.read_bytes())
    out.mkdir(parents=True, exist_ok=True)
    (out / "flash.bin").write_bytes(flash[APPLICATION:])
    (out / "config.bin").write_bytes(config)


def images(raw):
    """Returns the flash from address 0 and the configuration of every row."""
    rows, _ = runpy.run_path(str(INSPECT))["parse"](raw)
    flash = bytearray(b"\xff" * (ROWS * ROW_BYTES))
    config = bytearray(ROWS * ECC_BYTES)
    for index, data in rows.items():
        flash[index * ROW_BYTES:(index + 1) * ROW_BYTES] = data[:ROW_BYTES]
        config[index * ECC_BYTES:(index + 1) * ECC_BYTES] = data[ROW_BYTES:]
    return bytes(flash), bytes(config)


if __name__ == "__main__":
    main()
