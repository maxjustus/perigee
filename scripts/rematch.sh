#!/bin/bash
# Reload the vendor kext so that IOKit matches the Ensemble again. The best
# IOProbeScore wins: the dext if it is active, else the vendor kext.
#
# An unload alone is not enough. IOKit starts the new match before the
# vendor driver is gone, and the device stays without a driver. The load
# adds the vendor personalities again, and that starts a second match.
#
# "boot" waits up to 60 s for a driver and reloads only if the vendor driver
# has the device. At boot the vendor kext attaches before the dext is in the
# IOKit catalog. scripts/system.sh installs a launch daemon for this.
#
# Usage: sudo scripts/rematch.sh [boot]
set -uo pipefail

kext=com.apogeedigital.kextElementEnsemble

has() {
  ioreg -r "$@" | grep -q .
}

if [[ ${1:-} == boot ]]; then
  for _ in $(seq 60); do
    has -c com_apogeedigital_Ensemble2Device && break
    has -n EnsembleDriver && exit 0
    sleep 1
  done
fi
kmutil unload -b "$kext" 2> /dev/null
# kmutil load fails on any invalid kext in /Library/Extensions, also after
# it loads this one.
kmutil load -b "$kext" > /dev/null 2>&1
exit 0
