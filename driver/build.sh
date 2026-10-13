#!/usr/bin/env bash
# Build EnsembleHost.app with the embedded dext, and the ensemblectl tool,
# signed for a test Mac.
#
# The ad-hoc signature carries the entitlements without a provisioning
# profile. macOS accepts that only with SIP disabled and with
# `systemextensionsctl developer on`. A signature with a team ID fails:
# AMFI then requires a matching profile.
#
# Usage: driver/build.sh   (prints the path of the app)
set -euo pipefail
cd "$(dirname "$0")"

app=build/Build/Products/Debug/EnsembleHost.app
dext=$app/Contents/Library/SystemExtensions/dev.ensemble.Host.Driver.dext

xcodegen generate --quiet
env -u CC -u CXX xcodebuild -quiet -project Ensemble.xcodeproj -scheme EnsembleHost \
  -configuration Debug -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
codesign --force --sign - --entitlements EnsembleDriver/EnsembleDriver.entitlements "$dext"
codesign --force --sign - --entitlements EnsembleHost/EnsembleHost.entitlements "$app"
env -u CC -u CXX xcrun swiftc -O -o build/ensemblectl ensemblectl/main.swift
codesign --force --sign - --entitlements ensemblectl/ensemblectl.entitlements build/ensemblectl
echo "$PWD/$app"
