# Ensemble Thunderbolt hardware recovery

No verified hardware recovery path exists in the inspected evidence, and reverse engineering cannot provide an absolute non-brick guarantee.

## Explanation

### Scope and confidence

This report covers the Apogee Ensemble Thunderbolt, not the older FireWire Ensemble or the Element family.
All local inspection was offline. Research used public documents and source code. No device access, programmer operation, privileged command, or firmware change occurred.

- **Verified / high**: direct evidence in a vendor document, source code, or local file. A chip capability does not establish board access.
- **Inferred / medium**: a conclusion from cited evidence, without direct confirmation on this board.
- **Unknown**: the evidence does not establish the claim. Unknown recovery prerequisites block firmware changes.

Terms:

| Term | Meaning |
|---|---|
| PSoC | Cypress Programmable System-on-Chip microcontroller |
| FPGA | Field-programmable gate array, here the Cyclone V |
| SWD | Serial Wire Debug, a chip-level debug interface |
| JTAG | IEEE 1149.1 test interface, also used for chip configuration |
| EEPROM | Electrically erasable nonvolatile memory for persistent data |
| ECC | Error correction code space, also usable for PSoC configuration data |
| NVL | Nonvolatile latch for PSoC reset configuration |
| WOL | Write-once latch that can permanently disable external PSoC access |
| SFL | Serial Flash Loader, FPGA logic that bridges JTAG to configuration flash |
| AS | Active Serial, an FPGA configuration interface |
| CRC | Cyclic redundancy check, an error-detection value, not a proof of correct behavior |
| Recovery proof | A successful external restore after loss of the normal update path, on a spare board |

### Board identity and physical access

| Claim | Status and evidence | Recovery consequence |
|---|---|---|
| The updater targets PSoC silicon ID `0x2E12F069`. | **Verified / high**. `EnsemblePSoC.cyacd`, header at file offset 0: `2E12F0690000`. | Use the correct family documentation. |
| That ID maps to `CY8C5268AXI-LP047`, 100-TQFP, 67 MHz, 256 KB flash, 64 KB SRAM, 2 KB EEPROM. | **Verified / high**, identity table in the [CY8C52LP datasheet], printed p.105, table 12-1. The installed part is **Inferred / medium** from the updater target. | Obtain a legible package photo before a physical connection. |
| The FPGA target is Cyclone V GX `5CGXC3`. | **Inferred / medium** here. `E2FPGA.bin` contains 1,813,864 bytes, or 14,510,912 bits. `NOTES-vendor-driver.md:29` cites Cyclone V datasheet table 63 for this size. | Package, speed grade, temperature grade, and board revision remain **Unknown**. File length does not establish package pins. |
| A first-hand product review identifies an Altera Cyclone V. | **Verified / high** as a published claim, not a verified package inscription. [Audiofader review], “Hardware”: “L’FPGA è un Altera Cyclone V”. | This corroborates the family, not its suffix or debug access. |
| The review names OPA1612, THAT 5171, AK5388AEQ, Cirrus Logic 5361, and ES9016 SABRE. | **Inferred / medium** as board identities. [Audiofader review], “Hardware”. No legible chip photos corroborate these names in the inspected article. | Treat these as physical inspection targets, not a verified bill of materials. |
| The inspected review provides exterior, front-panel, rear-panel, and Maestro images. | **Verified / high**, article image links. No board photo or header pinout appears among those images. | The review is not evidence for a recovery connector. |
| PSoC SWD pads, FPGA JTAG pads, connector designators, and chain topology. | **Unknown**. No schematic, service manual, or legible board teardown established them in this research. | Do not assign header pins from connector shape or a generic evaluation board. |
| Configuration flash manufacturer, model, package, voltage, and write-protect circuit. | **Unknown**. Firmware exposes addresses and operations, not a physical part identity. | Do not assume EPCS, EPCQ, Winbond, 3.3 V, or a standard clip pinout. |
| Thunderbolt controller, its nonvolatile storage, and other programmable chips. | **Unknown** in the inspected evidence. | A backup of only the PSoC and FPGA payloads cannot establish full-board recovery. |

The local image search found generated front-panel assets, not board photographs.
Public search services returned challenges or irrelevant results. The absence of a located teardown does not prove that none exists.

### PSoC protection is not one lock

The [CY8C52LP datasheet], pp.20–21 and 56–59, separates flash protection, debug selection, debug enable, and permanent device security.

| Mechanism | Generic chip capability, Verified / high | Actual Ensemble access |
|---|---|---|
| SWD acquisition | Port signals are `P1[1]` clock and `P1[0]` data. An alternative uses `P15[7]` and `P15[6]`. Datasheet p.58. | **Unknown** pad access, attached loads, voltage domains, reset access, and active port. These are chip signal names, not a board pinout. |
| Reset acquisition window | The datasheet specifies an 8 µs key window after reset. Disabled GPIO-mode ports can be reacquired through SWD. Datasheet p.58. | **Unknown** fixture compatibility. Port acquisition does not override WOL security or prove memory access. |
| Debug configuration | `DPS` selects port mode. `DBGEN` controls debug access. NVLs also control reset drive states and ECC mode. Datasheet p.21. | **Unknown** installed NVLs. An application payload does not reveal their installed values. |
| Flash row protection | Four levels exist: Unprotected, Factory Upgrade, Field Upgrade, Full Protection. Datasheet p.20, table 5-1. | **Unknown** installed protection for each row. A normal update proves neither external read access nor external write access. |
| Debug versus test access | An enabled debug controller can read flash despite row protection. Write protection still applies. [PSoC architecture TRM], pp.156 and 160. | **Unknown** debug state. Do not trigger an erase merely because a programmer cannot read the target. |
| Protection reset | Flash protection reset requires complete flash erase. Datasheet p.59 and TRM p.159. | **Inferred / high risk**: an unlock workflow that uses this operation destroys the bootloader absent from the updater. |
| Permanent device security | WOL security permanently disables debug and test access. Datasheet p.59 and TRM pp.156, 160. | **Unknown** WOL state. Mass erase is not a recovery method for an active WOL. |
| Bootloader with WOL | A bootloader can still update rows that permit internal writes. TRM p.160, question 9. | **Inferred / medium**: vendor updates can succeed on a unit with no external restore path. |

A PSoC USB-capable pin pair does not establish a USB recovery port on the Ensemble.
A blank replacement PSoC does not contain the Apogee bootloader.
The [Bootloader application note], p.14, states that PSoC has no bootload ROM. Its supervisory services are not an Apogee recovery image.

### Erase scope and data preservation

| Operation or data | Evidence and confidence | Required decision |
|---|---|---|
| PSoC `Erase All`, command `0x09` | **Verified / high**: erases all flash data, ECC/configuration bytes, protection rows, and flash row latches. TRM p.403. | Reject before a complete recoverable backup exists. It is not a read-unlock operation. |
| EEPROM versus `Erase All` | **Verified / high**: the TRM assigns `0x09` to flash. EEPROM uses a separate array and separate write/erase operations. TRM pp.401–403. | Do not claim that this command necessarily erases EEPROM. Audit the complete programmer workflow for additional EEPROM operations. |
| Programmer “recover”, “unlock”, or “program” actions | **Unknown** exact behavior until the tool, version, configuration, and commands are reviewed. The [PSoC device specification], p.25, includes full flash erase in its standard flow. | Disable automatic erase and automatic protection changes before any future backup attempt. |
| Silicon factory trim | **Verified / high**: manufacturing NVLs and reserved flash hold chip-specific trim. TRM pp.137–138. | Keep silicon trim separate from Apogee calibration. Do not copy undocumented factory regions from another chip. |
| Factory trim after an arbitrary tool workflow | **Unknown** for the selected tool and exact operation. The documented flash erase scope is not proof that all factory trim is erased. | Obtain the tool's documented exclusions and prove preservation on a spare. |
| Apogee calibration | **Unknown** storage locations, format, checksums, and per-unit content. | Preserve all accessible nonvolatile storage, including unused areas. A user preset is not a calibration backup. |
| Saved control values | **Verified / high**: `FUN_00020b78` reads EEPROM at `0x40008000`, validates its structure and checksum. `FUN_00020d18` replays records. | Capture all 2 KB, not only decoded values. Record bytes before and after each spare-board test. |
| Hardware identity | **Verified / high**: `FUN_00011b74` reads FPGA addresses `0x60800018` down to `0x60800011`. | **Unknown** ultimate source: FPGA chip ID, external flash, or another storage device. Preserve identity evidence before changes. |
| Host-reported ID | **Verified / high** in prior local evidence: `probe-results.md`, “Kernel panic in the vendor kext”, identifies a stale eighth byte. | Do not treat that byte as a stable factory identifier. Do not repeat the unsafe Get-all probe for this research. |
| Reset to defaults | **Verified / high** in `NOTES-vendor-driver.md:696`, command `0x51` calls `0x205CC` and saves defaults. | A factory-reset command is not firmware recovery or proof of calibration preservation. |

## Reference

### Offline payload coverage

The updater resources reside under `/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/`.

| Artifact | Verified / high observation | Missing recovery material |
|---|---|---|
| `EnsemblePSoC.cyacd` | 355 records, each with 288 data bytes. All record checksums passed the offline byte-sum check. | No complete factory image. |
| PSoC array 1 | Rows 0–255, flash `0x10000–0x1FFFF`. | Array 0 is absent. |
| PSoC array 2 | Rows 0–97, flash `0x20000–0x261FF`. | Rows 98–255 are absent. |
| PSoC array 3 | Only row 255, flash `0x3FF00–0x3FFFF`, the bootloadable metadata row. | Other array 3 rows are absent. |
| PSoC bootloader | No array 0 records, flash `0x00000–0x0FFFF`. [Bootloader application note], p.24, confirms that `.cyacd` excludes its associated bootloader. | Bootloader bytes and their configuration data. |
| `/tmp/apogee-fw/flash.bin` | 196,608-byte derivative, base address `0x10000`. | Not a device dump. Absent payload rows become `0xFF`. |
| `/tmp/apogee-fw/config.bin` | 32,768-byte derivative, 32 bytes per row across four arrays. | Not a full configuration backup. Absent rows become zero, including array 0. |
| `E2FPGA.bin` | 1,813,864 bytes. | No proof of the complete external flash layout or lower recovery image. |
| `EnsembleResourceData.bin` | 230,036 bytes. | No proof of all external resource storage or per-unit data. |

Derivative behavior is explicit in `scripts/ghidra/psoc-images.py:25–36`: `flash = bytearray(b"\xff" * (ROWS * ROW_BYTES))` and `config = bytearray(ROWS * ECC_BYTES)`.

SHA-256 values identify the inspected vendor files, not the contents of the unit:

```text
EnsemblePSoC.cyacd
7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24
E2FPGA.bin
b3ef52ae2d1e255307e286d92f2dc92f8dccc06f0f58f7eb1c55a6cbbc4ffdf2
EnsembleResourceData.bin
3febcf6f14123ca9767fe651a87fc6fd5ba875dbe52fadf0b3160ce73bdb290b
```

### External flash and update dependencies

| Claim | Status and exact evidence |
|---|---|
| The application selects FPGA update base `0x1C0000` and resource base `0x380000`. | **Verified / high**, `FUN_000183f4` and `FUN_00017fb4`. |
| The update range checks stop FPGA writes below `0x380000` and resource writes below `0x800000`. | **Verified / high**, `FUN_0001836c`. These limits do not identify flash capacity. |
| The application erases on `0x10000` boundaries and transfers 256-byte buffers. | **Verified / high**, `FUN_00018098`, calls to `FUN_000123e0` and `FUN_00012444`. Physical erase geometry remains **Inferred / medium**. |
| Flash access depends on FPGA logic at `0x6080002E–0x60800034` and buffer `0x60800C00`. | **Verified / high**, `FUN_00012334`, `FUN_00012444`, and `FUN_000124dc`. |
| The lower external region contains a factory fallback image. | **Unknown**. The update base leaves `0x000000–0x1BFFFF` outside this application update range, but its contents are absent. |
| An intact PSoC can restore a dead FPGA through the normal host path. | **Unknown**, and unsafe to assume. Both the flash bridge and host transport depend on FPGA behavior. |
| PSoC update entry uses application code. | **Verified / high**, `FUN_00017fb4(0)` writes FPGA register `0x6080002D` then calls `FUN_000232fc`. Independent forced entry is **Unknown**. |
| The installed bootloader recovers after interrupted writes. | **Unknown**. Generic Creator behavior waits for another update after an invalid application, [Bootloader application note], p.15. The installed bootloader is absent. |
| A valid checksum proves safe execution. | **False as an inference**. Byte integrity does not prove register compatibility, bounds, reset states, or analog output safety. |

The [Bootloader application note], pp.26–28, describes optional dual-application support. It does not prove that Apogee enabled it.

### Cyclone V recovery: capability versus access

All generic capabilities below come from the [Cyclone V handbook], revision 2023.10.18, or [Serial Flash Loader application note].

| Path or limit | Generic capability, Verified / high | Ensemble prerequisite or gap |
|---|---|---|
| JTAG configuration | JTAG takes precedence over other configuration schemes. Handbook p.7-34. | **Unknown** usable pads, chain, supplies, reset conditions, and security state. |
| Volatile FPGA load | JTAG can load an SRAM Object File. Handbook p.7-34. | A temporary load does not repair external flash. A bad design can still drive unsafe board signals. |
| FPGA backup | Configuration readback is unsupported. Handbook p.7-45. | Do not promise a live FPGA bitstream dump over JTAG. Back up the external configuration storage instead. |
| SFL recovery | SFL logic must bridge JTAG to the AS interface. Handbook p.7-25. Application note pp.3–4. | **Unknown** flash compatibility, AS wiring, and permission to load SFL. An IDCODE response is insufficient. |
| Direct flash recovery | The handbook describes direct AS access, pp.7-27–7-29. | **Unknown** physical part and board isolation. A clip can back-power the board or contend with an active controller. |
| Remote fallback | A user-defined factory image, application image, selected remote mode, and control logic form the recovery system. Handbook pp.7-39–7-44. | **Unknown** implementation, lower image, image protection, and watchdog policy. Chip support alone is not fallback proof. |
| JTAG voltage | Bank 3A `VCCPD` powers TDI, TDO, TMS, and TCK. Supported supplies include 2.5, 3.0, and 3.3 V. Handbook p.9-8. | **Unknown** actual voltage. Do not use the PSoC rail as the FPGA reference without measurement. |
| Reset and identification | Low `nCONFIG` or `nSTATUS` can prevent a correct IDCODE read. Handbook p.9-7. | A failed scan does not prove permanent lock or a dead FPGA. |
| Security on this unit | The handbook describes possible chip configurations, not Apogee's installed security policy. | **Unknown**. No inspected evidence establishes encryption, programmed keys, tamper protection, or JTAG secure mode on this unit. |
| Encryption and permanent keys | Nonvolatile keys are one-time programmable. Tamper protection is irreversible. Handbook pp.7-45–7-48. | **Unknown** installed key and tamper state. Do not alter keys or security bits. |
| Secure-mode unlock | The instruction table restricts `UNLOCK` to internal JTAG core access in user mode. Handbook p.9-7. | Do not assume an external probe can unlock a failed secured design. The surrounding prose is less precise than this table. |
| Private instructions | The vendor warns that specified private instructions can damage the device. Handbook p.9-7. | Do not brute-force JTAG instructions. |

A generic programmer can also destroy PSoC configuration data.
The inspected [OpenOCD PSoC source] is pinned to commit `2075427d1585dc1bc17f75a51df91a1b20b4ad4b`.

| Behavior | Verified / high source evidence |
|---|---|
| Reject direct ECC-region writes | `psoc5lp_write`, lines 1129–1132: `if (offset + byte_count > bank->size)` returns `ERROR_FLASH_DST_OUT_OF_BANK`. |
| Replace configuration bytes with a default | `psoc5lp_write`, lines 1140–1144: `memset(ecc_bytes, bank->default_padded_value, ROW_ECC_SIZE)` executes when ECC is disabled. |
| Transfer the replacement bytes | `psoc5lp_write`, lines 1218–1224: `target_write_buffer` appends `ecc_bytes` after the 256 data bytes. |
| Default to zero | [OpenOCD flash defaults], line 1425: `bank->default_padded_value = bank->erased_value = 0x00`. |
| Configuration byte count | [OpenOCD row sizes], line 91: `#define ROW_ECC_SIZE       32`. |

These claims apply to that commit, not every OpenOCD release or user configuration.
The default write flow supplies zeros, not the saved configuration bytes.
Do not assume that a raw `flash.bin` write restores the 32 configuration bytes per row.

SHA-256 of the pinned `src/flash/nor/psoc5lp.c`:

```text
99259a9445da6b1977a94b23449f4e5345eb063079b771924dd0b0cb2dc46ac6
```

## Safety notes

- Do not unlock or mass-erase the PSoC before recovery proof. The operation can destroy the only Apogee bootloader.
- Do not alter WOL, FPGA keys, tamper protection, or undocumented JTAG instructions. These can remove future recovery access permanently.
- Do not substitute zero-filled `config.bin` gaps for device data. Those bytes are synthetic, not observed flash contents.
- Do not rely on the vendor updater after FPGA failure. Its transport and flash access can depend on the failed design.
- Do not attach a programmer before voltage and net identification. Incorrect voltage, back-power, or output contention can damage chips.
- Do not open or probe the powered chassis without a qualified service procedure. The power supply can expose hazardous voltage.
- Disconnect speakers, headphones, microphones, and other external analog loads before any future firmware experiment.
- Treat phantom power, relay control, output mute, and power sequencing as safety-critical signals.
  `NOTES-vendor-driver.md:663–680` maps several such controls to FPGA registers and external analog devices.
- Treat debug halt, reset, FPGA configuration, and boundary-scan output control as intrusive operations, even without flash writes.

## Proposed tests and verification ladder

These are future gates, not authorization to access the unit.
No executable hardware command is specified because the physical interface, voltage, tool, and protection state remain unknown.
A fabricated command can select an erase flow or the wrong target.
Before a hardware gate, approve an exact tool command list and its erase exclusions for the inspected spare-board fixture.

### Offline validation gate

- Preserve the vendor package and record hashes.
- Validate every `.cyacd` record, silicon ID, row size, checksum, duplicate, address, and metadata field.
- Keep absent rows distinct from erased rows.
- Verify PSoC code and configuration bytes together.
- Audit startup pin states, watchdogs, flash routines, update bounds, and all firmware-controlled analog outputs.
- Compare FPGA device, package, pin constraints, clocks, and reset behavior against physical evidence.
- Reject changes without a complete delta and a list of all nonvolatile writes.

Safe local hash command:

```sh
shasum -a 256 \
  '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsemblePSoC.cyacd' \
  '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/E2FPGA.bin' \
  '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsembleResourceData.bin'
```

Risk: none to the device. This command reads local files only.
Pass evidence: reproducible artifacts, validated payload structure, and reviewed hardware dependencies. This gate cannot prove physical recovery.

### Behavioral comparison gate

- Compare modified code with the vendor baseline in an offline model first.
- Exercise normal, malformed, boundary, timeout, and reset inputs.
- Compare register writes, message traces, mute behavior, persistent data, and metadata updates.
- Use an isolated spare fixture for behavior that the model cannot reproduce.

Risk: a model omits analog effects and undocumented chip behavior. A live spare test can reset the device or drive unsafe outputs.
Pass evidence: explained differences, bounded writes, safe output transitions, and no unexplained persistent changes.

### External backup and restore gate

- Use a spare board with the same verified revision.
- Capture two independent reads of every accessible nonvolatile region.
- Compare hashes and investigate unstable bytes before any erase.
- Preserve complete PSoC flash, row configuration, EEPROM, protection state, and readable NVLs.
- Preserve entire external flash devices, status registers, and readable identity or one-time regions.
- Record inaccessible factory regions and obtain evidence that the restore flow cannot alter them.
- Restore through a path independent of the normal updater, then prove cold boot and baseline behavior.
- Prove restoration of the bootloader, metadata, configuration bytes, persistent values, IDs, and calibration-dependent audio performance.

Risk: erase, incorrect restoration, fixture damage, and permanent loss of the spare.
Pass evidence: repeatable external restoration after the normal update path is unavailable. A successful backup alone does not pass.
If protection prevents a complete backup, stop. Require a vendor recovery image and a proven authorized recovery path.

### Fault injection gate

- Start with offline fault simulation.
- On the proven spare fixture, interrupt each erase, page write, metadata commit, and reset transition.
- Test corrupt images, missing application data, transport loss, watchdog expiry, and loss of normal FPGA communication.
- Restore the baseline externally after each induced failure.
- Verify calibration, identity, persistence, and audio safety after each restore.

Risk: deliberate loss of normal boot or update access, persistent corruption, and hardware damage.
Pass evidence: a failure matrix with repeatable recovery at each tested boundary. Untested failures remain risks.

### Gated unit-change stage

- Obtain owner approval for the exact image, exact command list, and documented residual risks.
- Require that the spare-board restore procedure matches the unit's revision and security state.
- Obtain a unit-specific backup before any write.
- Preserve bootloader, fallback region, protection, keys, calibration, and IDs during the first change.
- Change one bounded behavior at a time.
- Compare the complete post-change evidence with the baseline.
- Stop on any unexplained difference.

Risk: the original unit can still become unusable despite all prior gates.
No test sequence or reverse-engineered model provides an absolute non-brick guarantee.

### Physical inspection checklist

This checklist requires separate owner authorization. No listed physical inspection occurred in this task.

- [ ] Confirm Thunderbolt model, serial label, and every board revision.
- [ ] Photograph both board sides, connectors, test pads, and component inscriptions at readable resolution.
- [ ] Identify the PSoC package and the complete FPGA part number.
- [ ] Identify every flash, EEPROM, supervisor, programmable logic device, and Thunderbolt controller.
- [ ] Record each memory's voltage, capacity, erase geometry, protection features, and immutable regions from its own datasheet.
- [ ] Identify ground and reference rails before any signal connection.
- [ ] Trace candidate debug pads by unpowered continuity tests to verified chip signals.
- [ ] Record each pad's coordinates, label, net evidence, series components, pull resistors, and attached devices.
- [ ] Confirm PSoC reset access and both candidate SWD port routes without a guessed connector map.
- [ ] Confirm FPGA TDI, TDO, TMS, TCK, chain order, `nCONFIG`, `nSTATUS`, and `CONF_DONE` routes.
- [ ] Record FPGA mode straps and the physical path from configuration flash to the FPGA.
- [ ] Identify flash bus owners and a proven means of electrical isolation.
- [ ] Check for a battery or rail that preserves FPGA key state before any disconnection.
- [ ] Establish safe states for power controls, relays, mute, converters, and phantom power during halt or reset.
- [ ] Audit the chosen programmer's default initialization, erase, unlock, and verification actions before connection.
- [ ] Stop if a tool requests erase to obtain access.

## Sources

Page references above use printed page numbers, unless explicitly marked as PDF pages.
The CY8C52LP datasheet and PSoC architecture TRM include an extra cover page in the downloaded PDF.
The Cyclone V handbook uses chapter-page numbers, such as 7-45 and 9-7.

| Source | Revision and evidence used |
|---|---|
| [CY8C52LP datasheet] | 001-84933 Rev. *P. Identity p.105. Memory pp.20–21. Debug and security pp.56–59. |
| [PSoC architecture TRM] | 001-78426 Rev. *G. Factory trim pp.137–138. Protection pp.155–160. Flash commands pp.401–403. |
| [PSoC device specification] | 001-81290 Rev. *F. Standard flow p.25. EEPROM p.41. Erase p.50. NVLs pp.82–83. |
| [Bootloader application note] | AN73854, 001-73854 Rev. *N, 2023-12-01. No bootload ROM p.14. Recovery p.15. Payload scope p.24. |
| [Cyclone V handbook] | CV-5V2, 2023.10.18. Configuration chapter CV-52007 and JTAG chapter CV-52009. |
| [Serial Flash Loader application note] | AN-370, 2019.02.18, pp.3–6. |
| [Audiofader review] | Andrea Scansani, 2017-04-06, “Hardware” section and article image links. First-hand review, not a vendor schematic. |
| [OpenOCD PSoC source] | Commit `2075427d1585dc1bc17f75a51df91a1b20b4ad4b`, `src/flash/nor/psoc5lp.c:1118–1304`. ECC defaults and transfer behavior in `psoc5lp_write`. |
| Local vendor artifacts | `.cyacd` record addresses and file hashes above. `/tmp/apogee-fw/decompiled.c`, cited function addresses. |
| Existing repository evidence | `NOTES-vendor-driver.md` and `probe-results.md`. Prior observations only, no probes repeated. |

[CY8C52LP datasheet]: https://www.infineon.com/assets/row/public/documents/30/49/infineon-psoc5lp-cy8c52lp-datasheet-datasheet-en.pdf
[PSoC architecture TRM]: https://www.infineon.com/assets/row/public/documents/30/57/infineon-psoc5lp-architecture-trm-additionaltechnicalinformation-en.pdf
[PSoC device specification]: https://www.infineon.com/assets/row/public/documents/30/436/infineon-cy8c58lp-cy8c56lp-cy8c54lp-cy8c52lp-psoc-5lp-device-programming-specifications-programming-specifications-en.pdf
[Bootloader application note]: https://www.infineon.com/assets/row/public/documents/cross-divisions/42/infineon-an73854-psoc-introduction-to-bootloaders-applicationnotes-en.pdf
[Cyclone V handbook]: https://docs.altera.com/api/khub/maps/dvxWxDO1_JfCNh~DgmxAcw/attachments/ozHoJIyPFCMAkmEIi9_Cfw-dvxWxDO1_JfCNh~DgmxAcw/content
[Serial Flash Loader application note]: https://docs.altera.com/api/khub/maps/oyxzS8BJRSlHfiq4iw5NJQ/attachments/LLqjxh8d71tLcPVGTmaV9A-oyxzS8BJRSlHfiq4iw5NJQ/content
[Audiofader review]: https://www.audiofader.com/test-apogee-ensemble-thunderbolt-ridisegnata-per-lasciare-il-segno/
[OpenOCD PSoC source]: https://github.com/openocd-org/openocd/blob/2075427d1585dc1bc17f75a51df91a1b20b4ad4b/src/flash/nor/psoc5lp.c#L1118-L1304
[OpenOCD flash defaults]: https://github.com/openocd-org/openocd/blob/2075427d1585dc1bc17f75a51df91a1b20b4ad4b/src/flash/nor/psoc5lp.c#L1412-L1436
[OpenOCD row sizes]: https://github.com/openocd-org/openocd/blob/2075427d1585dc1bc17f75a51df91a1b20b4ad4b/src/flash/nor/psoc5lp.c#L90-L94
