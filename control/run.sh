#!/usr/bin/env bash
# Build ensemble-control, sign it for EnsembleDriver's user client, and run it.
# The ad-hoc entitlement needs SIP disabled, like the dext build.
set -euo pipefail
cd "$(dirname "$0")"
env -u CC -u CXX -u LLVM_CONFIG swift build -c release
binary=.build/release/ensemble-control
codesign --force --sign - --entitlements ensemble-control.entitlements "$binary"
exec "$binary"
