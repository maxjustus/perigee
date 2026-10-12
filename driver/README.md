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

## Check

The driver publishes the BAR0 `ID` register as the `ID` property:

    ioreg -l -w0 | rg -A12 '\+-o EnsembleDriver  <' | rg '"ID"'

The expected value is 2882400001 (0xABCDEF01).

## Return the device to the vendor driver

1. Run `<app>/Contents/MacOS/EnsembleHost deactivate`.
2. Replug the Thunderbolt cable.
3. Run `scripts/vendor-hal.sh on`.

The dext personality uses the vendor kext's `IOMatchCategory` with a higher
`IOProbeScore`. While the dext is active, the vendor kext does not attach.
