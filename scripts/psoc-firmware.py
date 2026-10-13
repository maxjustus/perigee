"""Disassembles the Ensemble PSoC 5LP firmware from the vendor updater.

Usage: python3 scripts/psoc-firmware.py [firmware.cyacd] > psoc.s

The .cyacd file holds 288-byte flash rows (256 data bytes, 32 ECC bytes).
Array 0 holds the bootloader and is not in the file, so the application
starts at 0x10000. The script wraps the image in an ELF object and runs
llvm-objdump from Xcode with addresses as on the device.
"""
import pathlib
import runpy
import subprocess
import sys
import tempfile

IMAGES = runpy.run_path(str(pathlib.Path(__file__).parent / "ghidra" / "psoc-images.py"))
APPLICATION = IMAGES["APPLICATION"]


def main():
    raw = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else IMAGES["DEFAULT"]).read_bytes()
    application = IMAGES["images"](raw)[0][APPLICATION:]
    print(f"@ silicon ID {raw[:8].decode()}", flush=True)
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
