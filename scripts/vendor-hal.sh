#!/usr/bin/env bash
# Switch the Apogee vendor HAL plugin on or off.
#
# On:  coreaudiod loads ApogeeElementEnsemble.driver. The Ensemble is a
#      normal audio interface.
# Off: the bundle is in /Library/Audio/Plug-Ins/HAL-disabled. coreaudiod
#      does not load it, and the Ensemble is not an audio device. The probe
#      is the only client of the kext.
#
# Usage:
#   scripts/vendor-hal.sh status  Show the bundle state and the kext client
#   scripts/vendor-hal.sh on      Put the bundle in the HAL folder, restart coreaudiod
#   scripts/vendor-hal.sh off     Move the bundle out, restart coreaudiod
#
# A probe run takes the kext client from the vendor HAL. Run "on" after
# each probe session, also when the bundle is in place: the coreaudiod
# restart gives the vendor HAL its client back.
#
# "on" and "off" use sudo. Quit audio apps first. The restart stops all
# audio on the Mac. "on" waits for the plugin to open the kext client, so
# the Ensemble must be attached.
set -euo pipefail

bundle=ApogeeElementEnsemble.driver
enabled=/Library/Audio/Plug-Ins/HAL
disabled=/Library/Audio/Plug-Ins/HAL-disabled

main() {
  case ${1:-} in
    status) status ;;
    on | off) switch "$1" ;;
    *)
      echo "usage: $0 status|on|off" >&2
      exit 2
      ;;
  esac
}

status() {
  echo "bundle: $(state)"
  echo "plugin process: $(pgrep -lf "Core Audio Driver \($bundle\)" || echo none)"
  ioreg -r -c com_apogeedigital_ElemEnsUserClient -l -w0 | grep IOUserClientCreator ||
    echo "kext client: none"
}

state() {
  if [[ -d $enabled/$bundle && -d $disabled/$bundle ]]; then
    echo both
  elif [[ -d $enabled/$bundle ]]; then
    echo on
  elif [[ -d $disabled/$bundle ]]; then
    echo off
  else
    echo missing
  fi
}

switch() {
  local want=$1 current
  current=$(state)
  case $current in
    "$want") ;;
    on) sudo mkdir -p "$disabled" && sudo mv "$enabled/$bundle" "$disabled/" ;;
    off) sudo mv "$disabled/$bundle" "$enabled/" ;;
    *)
      echo "bundle state is '$current'. Fix it by hand." >&2
      exit 1
      ;;
  esac
  local old
  old=$(pgrep -x coreaudiod || true)
  sudo launchctl kickstart -k system/com.apple.audio.coreaudiod
  wait_for "$want" "$old"
  status
}

wait_for() {
  local want=$1 old=$2 pid plugin loaded
  for _ in $(seq 40); do
    pid=$(pgrep -x coreaudiod || true)
    plugin=$(pgrep -f "Core Audio Driver \($bundle\)" || true)
    loaded=off
    [[ -n $plugin && $(ioreg -r -c com_apogeedigital_ElemEnsUserClient -l -w0) == *"pid $plugin,"* ]] &&
      loaded=on
    [[ -n $pid && $pid != "$old" && $loaded == "$want" ]] && return
    sleep 0.5
  done
  echo "coreaudiod did not reach state '$want' in 20 s" >&2
  exit 1
}

main "$@"
