#!/usr/bin/env bash
# Run the host-side unit tests for code that the dext shares.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
for test in protocol mailbox; do
  env -u CC -u CXX xcrun clang++ -std=c++20 -Wall -Wextra -Werror -I EnsembleDriver \
    "tests/${test}_test.cpp" -o "build/${test}_test"
  "build/${test}_test"
done
