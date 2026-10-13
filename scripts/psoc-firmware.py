"""Disassembles the Ensemble PSoC 5LP firmware from the vendor updater.

Usage: python3 scripts/psoc-firmware.py [firmware.cyacd] > psoc.s

The .cyacd file holds 288-byte flash rows (256 data bytes, 32 ECC bytes).
Array 0 holds the bootloader and is not in the file, so the application
starts at 0x10000. The script wraps the image in an ELF object and runs
llvm-objdump from Xcode with addresses as on the device.
"""
import pathlib
import subprocess
import sys
import tempfile

DEFAULT = "/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsemblePSoC.cyacd"
ROW_BYTES = 256
ROWS_PER_ARRAY = 256
APPLICATION = 0x10000


def flash_image(cyacd):
    lines = pathlib.Path(cyacd).read_text().split()
    image = bytearray(b"\xff" * (4 * ROWS_PER_ARRAY * ROW_BYTES))
    for line in lines[1:]:
        row = bytes.fromhex(line[1:])
        array, number = row[0], int.from_bytes(row[1:3], "big")
        address = (array * ROWS_PER_ARRAY + number) * ROW_BYTES
        image[address:address + ROW_BYTES] = row[5:5 + ROW_BYTES]
    return lines[0][:8], bytes(image[APPLICATION:])


def main():
    silicon_id, application = flash_image(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    print(f"@ silicon ID {silicon_id}", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "app.bin").write_bytes(application)
        (tmp / "app.s").write_text('.syntax unified\n.thumb\n.section .text,"ax",%progbits\n.incbin "app.bin"\n')
        subprocess.run(["xcrun", "clang", "-target", "thumbv7m-none-eabi", "-c", "app.s", "-o", "app.o"],
                       cwd=tmp, check=True)
        subprocess.run(["xcrun", "llvm-objdump", "-d", "--triple=thumbv7m-none-eabi",
                        f"--adjust-vma={APPLICATION:#x}", "app.o"], cwd=tmp, check=True)


if __name__ == "__main__":
    main()
