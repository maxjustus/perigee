# EnsembleDriver

`EnsembleHost.app` installs `EnsembleDriver`, a DriverKit extension (dext)
for the Apogee Ensemble Thunderbolt. `docs/adr/0001-one-audiodriverkit-dext.md`
records the design.

## Requirements

- SIP disabled and `systemextensionsctl developer on`. The build signs ad
  hoc, without a provisioning profile.
- Xcode with the DriverKit SDK, and `xcodegen`.

## Build and install

`make install` in the repository root builds, activates, and switches the
Ensemble to the dext. `README.md` describes it. `driver/build.sh` only
builds. It prints the path of the app. The dext build fails on a compiler
warning or a Clang Static Analyzer finding.

The dext personality uses the vendor kext's `IOMatchCategory` with a higher
`IOProbeScore`. IOKit compares drivers only when it matches the device. At
boot the vendor kext matches before the dext is in the catalog.
`scripts/rematch.sh` reloads the vendor kext, and the reload starts a new
match that the dext wins.

## Test

`driver/test.sh` builds and runs the host-side unit tests. They cover the
PSoC message parser and encoder in `EnsembleDriver/Protocol.h`. They run
under AddressSanitizer and UndefinedBehaviorSanitizer.

`driver/fuzz.sh [seconds]` fuzzes the message parser and the RX mailbox
with values that the PSoC controls, 60 s per target by default. It needs
Homebrew LLVM. A crash input goes to `driver/build/fuzz/crash-*`.

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

After a PSoC restart, the dext sends each subscriber a report of type 5
with no data, and then sends a Get-all. The vendor kext sends the same
type-5 message to its HAL plugin.

## Return the device to the vendor driver

Run `make uninstall` in the repository root.
