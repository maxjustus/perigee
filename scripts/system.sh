#!/usr/bin/env bash
# The root half of `make install` and `make uninstall`.
#
# "install" adds a launch daemon that gives the Ensemble to the dext at
# each boot (scripts/rematch.sh), and gives it to the dext now. The vendor
# HAL plugin must be off: its client keeps the vendor kext loaded. An
# activated build of the same version waits until the old dext exits, so
# "install" stops the old dext.
#
# "uninstall" removes the daemon and the dext, and gives the Ensemble back
# to the vendor driver. It removes the dext without the password dialog of
# a deactivation request. That works only with SIP disabled.
#
# Usage: sudo scripts/system.sh install|uninstall
set -euo pipefail
cd "$(dirname "$0")/.."

daemon=/Library/LaunchDaemons/dev.ensemble.rematch.plist
rematch=/usr/local/libexec/dev.ensemble.rematch

main() {
  case ${1:-} in
    install)
      [[ $(scripts/vendor-hal.sh status) == "bundle: off"* ]] || scripts/vendor-hal.sh off > /dev/null
      pkill -f 'dev.ensemble.Host.Driver.dext/dev.ensemble.Host.Driver' || true
      scripts/rematch.sh
      wait_for EnsembleDriver
      install -d /usr/local/libexec
      install -m 755 scripts/rematch.sh "$rematch"
      install -m 644 launchd/dev.ensemble.rematch.plist "$daemon"
      launchctl bootout system "$daemon" 2> /dev/null || true
      launchctl bootstrap system "$daemon"
      ;;
    uninstall)
      launchctl bootout system "$daemon" 2> /dev/null || true
      rm -f "$daemon" "$rematch"
      systemextensionsctl uninstall - dev.ensemble.Host.Driver || true
      scripts/rematch.sh
      wait_for com_apogeedigital_Ensemble2Device
      scripts/vendor-hal.sh on > /dev/null
      ;;
    *)
      echo "usage: $0 install|uninstall" >&2
      exit 2
      ;;
  esac
}

wait_for() {
  for _ in $(seq 40); do
    if ioreg -r -n "$1" | grep -q . || ioreg -r -c "$1" | grep -q .; then
      echo "$1 owns the Ensemble"
      return
    fi
    sleep 0.5
  done
  echo "$1 did not attach in 20 s. Replug the Ensemble." >&2
  exit 1
}

main "$@"
