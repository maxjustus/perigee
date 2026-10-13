#!/usr/bin/env bash
# Build the dext and move the Ensemble to the new build without a replug.
#
# A dext that owns the device keeps running until the device leaves. When
# the old dext dies, IOKit matches the device again, and the vendor kext can
# win that match. So the script unloads the vendor kext for this boot, then
# stops the old dext. The new build then takes the device.
#
# Uses sudo. The vendor kext loads again at the next boot.
set -euo pipefail
cd "$(dirname "$0")"

host=build/Build/Products/Debug/EnsembleHost.app/Contents/MacOS/EnsembleHost

driver_id() {
  ioreg -w0 | grep -o '+-o EnsembleDriver  <class IOUserService, id [^,]*' || true
}

./build.sh > /dev/null
"$host" activate
old=$(driver_id)
sudo kmutil unload -b com.apogeedigital.kextElementEnsemble 2> /dev/null || true
sudo pkill -f 'dev.ensemble.Host.Driver.dext/dev.ensemble.Host.Driver' || true
for _ in $(seq 20); do
  new=$(driver_id)
  if [[ -n $new && $new != "$old" ]]; then
    echo "EnsembleDriver attached"
    exit 0
  fi
  sleep 0.5
done
echo "EnsembleDriver did not attach. Replug the Ensemble." >&2
exit 1
