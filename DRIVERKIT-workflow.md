# DriverKit workflow for the Ensemble Thunderbolt

This document covers the macOS development cycle for [plan.md](plan.md).
It describes proposed work, not a tested driver or an approved entitlement request.
The repository currently contains research and a plan, not an Xcode project.

## 1. Choose the driver boundary

DriverKit extensions (`.dext` bundles) execute in user space.
The OS mediates hardware access through DriverKit and its transport frameworks.
A custom kernel extension is not necessary for PCI access. [1]

The Ensemble exposes a PCI device through Thunderbolt, so PCIDriverKit is the proposed transport.
Apple explicitly supports PCIe devices through Thunderbolt. [1]

Two audio designs remain possible:

| Design                                      | Consequence                                                                                                |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| PCIDriverKit dext plus `EnsembleHAL.driver` | Retains the current Rust HAL plan, but requires a custom user client and proof of access from the HAL host |
| PCIDriverKit plus AudioDriverKit            | Uses Apple's CoreAudio integration and removes the separate audio server plugin                            |

Apple states: “AudioDriverKit handles all of the necessary user client communication between the CoreAudio HAL and the driver extension”. [2]
This project does not yet establish which design fits the device and its required macOS versions.

Before the HAL implementation:

1. Select the minimum macOS version and supported Mac architectures.
2. Verify AudioDriverKit and PCIDriverKit API availability in that Xcode SDK.
3. Request the required entitlements from Apple.
4. Prove the selected audio design on a Mac with normal security controls.

## 2. Establish access and a test environment

Apple requires DriverKit entitlements, a transport entitlement, and a host app with the System Extension capability.
Entitlements in a source file alone do not grant access.
The code signature and provisioning profile must authorize them. [3]

| Target                           | Capability or entitlement                                                                                        |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Host app                         | `com.apple.developer.system-extension.install`                                                                   |
| PCI dext                         | `com.apple.developer.driverkit`, template sandbox entitlement, and `com.apple.developer.driverkit.transport.pci` |
| Custom client executable         | `com.apple.developer.driverkit.userclient-access`, with the dext bundle identifier                               |
| AudioDriverKit dext, if selected | Audio family entitlement in addition to the transport and DriverKit entitlements                                 |

The PCI entitlement contains PCI match dictionaries.
The proposed device match is `IOPCIPrimaryMatch = 0x220119C2`, subject to device verification. [1]
The match in `Info.plist` selects hardware. The entitlement authorizes access to that hardware.

Apple's client sample distinguishes restricted client access from `com.apple.developer.driverkit.allow-any-userclient-access` on the dext. [4]
A HAL plugin runs inside an Apple host process, not as the installer app.
The installer app's entitlements therefore do not establish HAL access.
The current plan needs a supported HAL access policy, or AudioDriverKit, before release.

For this independent driver, Apple approval for access to Apogee hardware remains an external dependency.
Local development with relaxed security does not prove eligibility for distribution. [3]

Test preparation:

1. Use a dedicated test Mac with a recoverable system and the physical Ensemble.
2. Record the macOS version, Xcode version, SDK version, hardware revision, and firmware revision.
3. Complete the vendor-driver probe from `plan.md` before the custom driver claims the device.
4. Remove or disable the vendor driver through its supported procedure before custom PCI tests.
5. Keep speaker gain low for initial audio tests.

PCIDriverKit requires a successful `IOPCIDevice::Open` before PCI access and grants exclusive access to that client. [1]
The vendor driver and the new dext cannot both own the PCI device for a comparison test.

## 3. Create the Xcode targets

The minimum deliverable has a macOS host app and an embedded DriverKit extension.
The host app installs and updates the extension through SystemExtensions. [3][5]
The existing HAL design also needs its separate audio plugin bundle and installation path.
SystemExtensions does not install that HAL plugin.

1. Create the host app and DriverKit extension targets with unique bundle identifiers.
2. Add PCIDriverKit to the extension target.
3. Define DriverKit interfaces in `.iig` files and implementations in C++.
4. Let Xcode run `iig` and compile the generated interfaces.
5. Configure the PCI personality and the corresponding entitlements.
6. Embed the dext at `Ensemble.app/Contents/Library/SystemExtensions/<bundle-id>.dext`.
7. Configure certificates and profiles for each target.
8. Add activation, replacement, approval, failure, and deactivation controls to the host app.

Apple's user-client sample supplies the app/dext structure and validated request examples. [4]
Its unchecked request paths are demonstrations, not a suitable interface for this driver.

## 4. Build, activate, verify, repeat

An Xcode build does not itself attach the driver to hardware.
Activation makes the extension available to the system. Device matching then starts the driver. [1][5]

For each iteration:

1. Build the host app and its embedded dext.
2. Increment the dext bundle version for an update.
3. Install the app in `/Applications`, unless the test Mac uses system-extension developer mode.
4. Launch the host app.
5. Submit an `OSSystemExtensionRequest.activationRequest` through `OSSystemExtensionManager`.
6. Approve the extension through the system prompt and the indicated System Settings pane.
7. Handle the replacement callback for an existing version.
8. If activation requires a reboot, reboot before the test.
9. Verify activation with `systemextensionsctl list`.
10. Verify the PCI service in IORegistry and the dext process separately.
11. Run the current hardware acceptance test.
12. Record the result with the driver version and test environment.

System Settings labels vary by macOS release.
An active extension in `systemextensionsctl list` does not prove a successful PCI match or audio operation. [1][5]

Useful read-only diagnostics:

```sh
systemextensionsctl list
system_profiler SPThunderboltDataType SPPCIDataType
ioreg -l -w 0 -r -c IOPCIDevice
ps -axo pid,comm
log show --last 10m --style compact --predicate 'process == "sysextd"'
```

Use Console or a driver-specific log predicate for device lifecycle errors.
Keep logs out of the real-time audio path.

### Local development exceptions

Apple documents two distinct development aids. [6]

| Aid                                | Scope                                                                                           |
| ---------------------------------- | ----------------------------------------------------------------------------------------------- |
| `systemextensionsctl developer on` | Relaxes the app location requirement for local builds                                           |
| SIP disabled on a test Mac         | Allows development with relaxed security validation, including the local-signature sample setup |

Developer mode is not entitlement approval and does not replace a valid release signature.
SIP changes reduce system protection. They are not a customer installation requirement.

If local development requires these exceptions:

1. Follow Apple's security instructions for the exact test Mac and macOS release. [6]
2. Restrict the exception to the test Mac.
3. Restore SIP before release validation.
4. Run `systemextensionsctl developer off` before release validation.

## 5. Debug the dext process

DriverKit permits user-space debugging on the development Mac.
Apple documents LLDB attachment after the system launches the extension. [6]

1. Find the dext process ID with `ps`.
2. Start `sudo lldb` on the configured test Mac.
3. Run `process attach --pid <PID>` in LLDB.
4. Set breakpoints in `Start`, the user-client methods, and `Stop`.
5. Detach before real-time audio measurements.

A breakpoint can stop hardware service while DMA continues.
Use an idle device for initial debugger tests.
A dext crash need not crash the kernel, but it does not guarantee harmless device behavior. [1]

## 6. Advance through hardware gates

The following gates refine section 3.3 of `plan.md`.
They are project acceptance criteria, not results.

| Gate            | Required evidence                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| Activation      | Expected signed version appears in the extension list                                                |
| PCI attach      | Exclusive open succeeds and `ID` equals the vendor-probe result                                      |
| Register access | PCIDriverKit accesses reach the expected BAR offsets                                                 |
| Client access   | The intended client can open the user client under normal security controls                          |
| DMA             | Prepared DMA segments meet device address and size constraints                                       |
| Interrupts      | MSI count and timestamp progression match the expected wrap rate                                     |
| Audio           | A 48 kHz analog loopback reproduces the test signal                                                  |
| Control         | Rate and clock changes survive a Get-all round trip                                                  |
| Lifecycle       | Stop/start, client exit, unplug/replug, sleep/wake, and driver replacement leave no active stale DMA |

PCIDriverKit supplies indexed register-access APIs, interrupt dispatch sources, and DMA commands. [1]
CPU virtual addresses are not device DMA addresses.
Use the addresses from a prepared `IODMACommand` and verify every returned segment against the hardware constraints.
Stop device DMA before completion and release of its memory resources.

The plan's direct BAR-window exposure to the HAL remains unproven.
Apple's PCI guidance uses PCIDriverKit register-access APIs rather than unrestricted device-memory access. [1]
A mailbox subrange also needs isolation from adjacent registers at the actual memory-map granularity.
Keep mailbox operations in the dext if a safe, supported client map cannot be established.

Hardware-free tests can cover packet parsing, argument validation, and state transitions.
They cannot establish PCI access, DMA correctness, or audio timing on the Ensemble.

## 7. Release and uninstall

Apple requires approved entitlements and compatible provisioning profiles for distribution. [3]
For direct distribution outside the Mac App Store, the release also needs Developer ID signatures and notarization. [7]

1. Archive the app and dext with release identities and profiles.
2. Verify the embedded extension's entitlements and signature.
3. Notarize the direct-distribution artifact and staple its ticket where supported.
4. Test a clean installation with SIP enabled and developer mode off.
5. Test approval, first attach, audio, an upgrade, and deactivation.
6. Submit a deactivation request through the host app for explicit driver removal.
7. If the system defers removal until reboot, reboot and verify removal.
8. Remove the separate HAL plugin through its own uninstall path if that design remains.

Do not copy a dext into `/Library/Extensions` or manually delete system-managed extension files.
Apple supports app-driven activation and deactivation, and removes associated extensions when the user deletes the app. [5]

## Sources

1. [Apple: Modernize PCI and SCSI drivers with DriverKit](https://developer.apple.com/videos/play/wwdc2020/10210/)
2. [Apple: AudioDriverKit](https://developer.apple.com/documentation/audiodriverkit)
3. [Apple: Requesting Entitlements for DriverKit Development](https://developer.apple.com/documentation/driverkit/requesting-entitlements-for-driverkit-development)
4. [Apple: Communicating between a DriverKit extension and a client app](https://developer.apple.com/documentation/driverkit/communicating-between-a-driverkit-extension-and-a-client-app)
5. [Apple: Installing System Extensions and Drivers](https://developer.apple.com/documentation/systemextensions/installing-system-extensions-and-drivers)
6. [Apple: Debugging and testing system extensions](https://developer.apple.com/documentation/driverkit/debugging-and-testing-system-extensions)
7. [Apple: Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
