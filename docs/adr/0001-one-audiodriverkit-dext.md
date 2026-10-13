---
status: accepted
---

# Drive the Ensemble with one PCIDriverKit and AudioDriverKit dext

One C++ DriverKit extension (dext) owns the PCI device and publishes the
CoreAudio device through AudioDriverKit. The dext also runs the PSoC
mailbox. There is no separate HAL plugin and no custom user client. The
probe results in `probe-results.md` show that the hardware fits the
AudioDriverKit clock and buffer model directly:

- `IOUserAudioStream::Create` takes an `IOMemoryDescriptor` that the HAL
  maps for audio IO. The dext gives it the DMA ring. The HAL then reads
  and writes 32-bit frames at `sampleTime mod 0x4000`, as the vendor HAL
  does. The dext has no code on the real-time IO path.
- `SetZeroTimeStampPeriod(0x4000)` matches the one MSI per ring wrap that
  the probe measured (341.3 ms at 48 kHz). The MSI handler calls
  `UpdateCurrentZeroTimestamp` with the time that
  `IOInterruptDispatchSource` passes. That time comes from the kernel's
  primary interrupt handler, so the latency of the dext process does not
  enter the timestamp.
- The sample rate maps to `PerformDeviceConfigurationChange` and PSoC
  command 0x29. The clock source maps to a `ClockSourceControl` selector.
  `SetElementName` gives the channel names.

## Considered options

- **Rust `AudioServerPlugIn` with a dext user client.** This is the
  fallback in `plan.md` section 3. It adds a user client, a mailbox window
  or a mailbox call interface, a DMA mapping into another process, and an
  installer path outside SystemExtensions. Its client runs in a
  `coreaudiod` helper, which cannot hold
  `com.apple.developer.driverkit.userclient-access`. So the dext needs
  `com.apple.developer.driverkit.allow-any-userclient-access`, which Apple
  also grants. The fallback needs as much Apple approval as this design.
  Use it only if a requirement excludes AudioDriverKit.
- **A kernel extension, as the vendor uses.** Rejected. Third-party kexts
  need reduced security on Apple silicon.

## Consequences

- The primary target is the last few macOS releases on Apple silicon.
  Intel Macs are a secondary target. AudioDriverKit starts at macOS 12
  (DriverKit 21.0). macOS 12 is also the last release for the Mac Pro
  (Late 2013), so the design does not exclude that Mac.
- DriverKit has no physically contiguous allocation. The FPGA takes one
  base address per ring. The design needs `IODMACommand::PrepareForDMA`
  to return one IOMMU segment for each ring. The vendor kext rings sit at
  IOVA 0x80000000 and 0x80224000, so the IOMMU maps them as one range on
  Apple silicon. The DMA step in `plan.md` section 3.3 must verify this
  for the dext, and on Intel Macs if they are in scope.
- `IOUserAudioCustomProperty` accepts `OSString`, `OSDictionary`, and
  `OSData` values. The Apogee Control app reads 32-bit integers and
  strings through property lists. Compatibility with Apogee Control is
  unverified. It is an optional step.
- Apple ties DriverKit entitlements to "your company's hardware vendor ID".
  Apogee owns vendor ID 0x19C2. Distribution therefore depends on Apple
  approval that this project does not control. Local development works
  with SIP disabled and `systemextensionsctl developer on`.
- The vendor kext matches the device with `IOProbeScore` 1000. Tests of
  the dext need the vendor kext disabled. `scripts/vendor-hal.sh` switches
  only the vendor HAL plugin.
