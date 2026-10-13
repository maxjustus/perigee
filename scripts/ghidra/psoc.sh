#!/bin/sh
# Builds a Ghidra project of the vendor PSoC firmware and exports its C.
# Usage: scripts/ghidra/psoc.sh [out dir]   (default /tmp/apogee-fw)
# Needs: brew install ghidra
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-/tmp/apogee-fw}
trm=$out/cydevice_trm.h
mkdir -p "$out"
python3 "$here/psoc-images.py" "$out"
[ -f "$trm" ] || curl -fsSL -o "$trm" \
    https://raw.githubusercontent.com/Infineon/CyScope/master/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/cydevice_trm.h
rm -rf "$out/ghidra"
mkdir -p "$out/ghidra"
"$(brew --prefix ghidra)/libexec/support/analyzeHeadless" "$out/ghidra" psoc \
    -import "$out/flash.bin" -processor ARM:LE:32:Cortex -loader BinaryLoader \
    -loader-baseAddr 0x10000 -scriptPath "$here" \
    -preScript PSoCSetup.java "$out" "$trm" \
    -postScript ExportDecompiled.java "$out"
