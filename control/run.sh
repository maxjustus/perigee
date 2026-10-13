#!/usr/bin/env bash
# Build ensemble-control, sign it for EnsembleDriver's user client, and run it.
# The service exits when the driver goes away. This loop starts it again,
# so a driver reload only drops the clients for a moment.
# The ad-hoc entitlement needs SIP disabled, like the dext build.
set -euo pipefail
cd "$(dirname "$0")"
env -u CC -u CXX -u LLVM_CONFIG swift build -c release
binary=.build/release/ensemble-control
codesign --force --sign - --entitlements ensemble-control.entitlements "$binary"
while true; do
  "$binary" || true
  sleep 2
done
