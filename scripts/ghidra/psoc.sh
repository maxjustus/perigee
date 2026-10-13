#!/bin/sh
# Builds a Ghidra project of the vendor PSoC firmware and exports its C.
# Usage: scripts/ghidra/psoc.sh [out dir]   (default /tmp/apogee-fw)
# Needs: brew install ghidra
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-/tmp/apogee-fw}
trm=$out/cydevice_trm.h
if [ -e "$out/ghidra" ] || [ -L "$out/ghidra" ]; then
    printf 'Analysis project already exists: %s\nChoose a new output directory.\n' "$out/ghidra" >&2
    exit 1
fi
mkdir -p "$out"
python3 "$here/psoc-images.py" "$out"
[ -f "$trm" ] || curl -fsSL -o "$trm" \
    https://raw.githubusercontent.com/Infineon/CyScope/0c0053d2f99b15c87bbfe410d49d4f091237d0f9/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/cydevice_trm.h
mkdir -p "$out/ghidra"
"$(brew --prefix ghidra)/libexec/support/analyzeHeadless" "$out/ghidra" psoc \
    -import "$out/flash.bin" -processor ARM:LE:32:Cortex -loader BinaryLoader \
    -loader-baseAddr 0x10000 -scriptPath "$here" \
    -preScript PSoCSetup.java "$out" "$trm" \
    -postScript ExportDecompiled.java "$out"
