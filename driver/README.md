# EnsembleDriver

`EnsembleHost.app` installs `EnsembleDriver`, a DriverKit extension (dext)
for the Apogee Ensemble Thunderbolt. `docs/adr/0001-one-audiodriverkit-dext.md`
records the design.

## Requirements

- SIP disabled and `systemextensionsctl developer on`. The build signs ad
  hoc, without a provisioning profile.
- Xcode with the DriverKit SDK, and `xcodegen`.

## Build and install

1. Run `driver/build.sh`. It prints the path of the app.
2. Run `<app>/Contents/MacOS/EnsembleHost activate`.
3. If the system asks, approve the driver in System Settings > General >
   Login Items & Extensions.
4. Replug the Thunderbolt cable.

IOKit compares drivers only when the device appears. A dext that owns the
device keeps running until the device leaves, so each new build needs a
replug.

## Test

`driver/test.sh` builds and runs the host-side unit tests. They cover the
PSoC message parser and encoder in `EnsembleDriver/Protocol.h`.

## Check

The driver publishes the BAR0 `ID` register as the `ID` property:

    ioreg -l -w0 | rg -A12 '\+-o EnsembleDriver  <' | rg '"ID"'

The expected value is 2882400001 (0xABCDEF01).

`swift driver/check.swift` finds the CoreAudio device named "Ensemble",
prints its channels, rate, and safety offsets, and runs 5 s of IO with
silent output. Expect 34 inputs, 36 outputs, about 48000 frames/s, and
0 overloads.

`driver/build/ensemblectl getall` opens the driver's user client, sends a
Get-all, and prints every PSoC report for 2 s. `ensemblectl set <command>
<p1> <value>` sends one type-1 command, for example `set 0x12 2 1` to mute
the speaker output.

## Return the device to the vendor driver

1. Run `<app>/Contents/MacOS/EnsembleHost deactivate`.
2. Replug the Thunderbolt cable.
3. Run `scripts/vendor-hal.sh on`.

The dext personality uses the vendor kext's `IOMatchCategory` with a higher
`IOProbeScore`. While the dext is active, the vendor kext does not attach.
