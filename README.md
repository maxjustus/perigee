# Open driver for the Apogee Ensemble Thunderbolt

This repository holds an open macOS driver for the Apogee Ensemble
Thunderbolt and a LAN control service for it. Apogee no longer supports
this model.

- `driver/`: a DriverKit extension (dext). It publishes the Ensemble to
  CoreAudio. See `driver/README.md`.
- `control/`: the control service. It gives a web UI on port 8737,
  JSON-RPC on port 8738, and a remote monitor stream on port 8739. See
  `control/README.md`.
- `NOTES-vendor-driver.md`: the device protocol.
- [Firmware map](docs/firmware/README.md): offline analysis, image checks,
  and unresolved recovery requirements.
- [Send-channel guard plan](docs/plan-send-channel-guards.md): close the
  user client send channel against the confirmed firmware parser defects.

## Requirements

- SIP disabled and `systemextensionsctl developer on`. The builds sign ad
  hoc, without a provisioning profile.
- Xcode with the DriverKit SDK, and `xcodegen`.
- The vendor driver installed. The open driver uses the vendor kext to
  switch between the two drivers.

## Use the open driver

    make install

The command builds the dext and the control service, activates the dext,
and gives the Ensemble to it. It asks for the sudo password. Quit audio
apps first: the switch stops all audio on the Mac for a moment.

If the command prints "approve the driver in System Settings", go to
System Settings > General > Login Items & Extensions > Driver Extensions.
Turn on EnsembleHost. The command then continues.

After `make install`:

- A launch daemon gives the Ensemble to the dext at each boot.
- A launch agent runs the control service at login and restarts it when
  it stops. Its log is `~/Library/Logs/ensemble-control.log`.
- The vendor HAL plugin is off.
- `~/Applications/Ensemble Mixer.app` opens the web UI in your browser.
  Press Cmd+Space and type "Ensemble Mixer".

Run `make install` again to install a new build. No replug is necessary.

## Return to the vendor driver

    make uninstall

The command removes the launch agent, the launch daemon, Ensemble
Mixer, and the dext. It
then gives the Ensemble to the vendor driver and turns the vendor HAL
plugin on. It asks for the sudo password. The next `make install` needs
the approval in System Settings again.

## Status

    make status

The command shows the dext, the driver that owns the Ensemble, the launch
daemon, the control service, and the vendor HAL plugin.
