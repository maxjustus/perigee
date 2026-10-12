#!/usr/bin/env bash
# Run the host-side unit tests for code that the dext shares.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
env -u CC -u CXX xcrun clang++ -std=c++20 -Wall -Wextra -Werror -I EnsembleDriver \
  tests/protocol_test.cpp -o build/protocol_test
build/protocol_test
