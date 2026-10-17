# perigee

This repository holds an open macOS driver for the Apogee Ensemble
Thunderbolt and a LAN control service for it. Apogee no longer supports
this model.

- `driver/`: a DriverKit extension (dext). It publishes the Ensemble to
  CoreAudio. See `driver/README.md`.
- `control/`: the control service. It gives a web UI on port 8737,
  JSON-RPC on port 8738, and a remote monitor stream on port 8739. See
  `control/README.md`.
- `probe/`: a tool that reads the Ensemble through the vendor kext. See
  `probe/README.md`.
- `NOTES-vendor-driver.md`: the device protocol.
- [Firmware map](docs/firmware/README.md): offline analysis, image checks,
  and unresolved recovery requirements.

## Requirements

- SIP disabled and `systemextensionsctl developer on`. The builds sign ad
  hoc, without a provisioning profile.
- Xcode with the DriverKit SDK, and `xcodegen`.
- Node.js and npm, to build the web UI.
- For `make test` and `make check`: `uv`, Rust with `cargo`, and
  Homebrew LLVM (`brew install llvm`) for the fuzzers.
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

## Build and test

No target in this list needs the Ensemble, except `make dev`.

| Command | Result |
|---------|--------|
| `make build` | Builds the web UI, the control service and the dext. It installs nothing. |
| `make service` | Builds the web UI and the control service only. |
| `make test` | Runs the web UI, control service, driver host, probe and Python tests. |
| `make lint` | Runs the strict TypeScript check, the Swift build with warnings as errors, `cargo clippy` and `ruff check`. |
| `make fuzz` | Fuzzes the driver's PSoC parser and RX mailbox, `FUZZ_SECONDS` per target (default 30). |
| `make check` | Runs `lint`, `test` and `fuzz`. |
| `make dev` | Runs the control service in the foreground with a live web UI build. |

`make test` leaves out `scripts/firmware/fpga-reconstruction-test.py`,
because that test needs an external Mistral checkout.

`make dev` stops the launch agent, because the service holds the ports.
It rebuilds the page on each change in `control/web`, and the service
reads the page on each request, so a browser reload shows the change.
Ctrl-C stops the service and starts the launch agent again.
