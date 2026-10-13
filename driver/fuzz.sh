#!/usr/bin/env bash
# Fuzz the code that reads PSoC data. Apple clang has no libFuzzer, so this
# uses Homebrew LLVM (`brew install llvm`).
#
# Usage: driver/fuzz.sh [seconds per target, default 60]
set -euo pipefail
cd "$(dirname "$0")"
clang=$(brew --prefix llvm)/bin/clang++
mkdir -p build/fuzz
for target in parse mailbox; do
  "$clang" -std=c++20 -Wall -Wextra -Werror -I EnsembleDriver -isysroot "$(xcrun --show-sdk-path)" \
    -g -O1 -fsanitize=fuzzer,address,undefined -fno-sanitize-recover=all \
    "fuzz/${target}_fuzz.cpp" -o "build/fuzz/$target"
  mkdir -p "build/fuzz/${target}_corpus"
  "build/fuzz/$target" -max_total_time="${1:-60}" -artifact_prefix=build/fuzz/ \
    "build/fuzz/${target}_corpus"
done
