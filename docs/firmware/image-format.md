# Ensemble PSoC image format

The vendor file passes record and application checksum checks, but it is neither a complete device backup nor proof of safe firmware.

## Scope and evidence

**Verified:** This report covers `EnsemblePSoC.cyacd` from `/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/`.
CYACD is Cypress's ASCII hexadecimal container for bootloadable application rows.
PSoC names the Cypress microcontroller family.
ECC means error-correcting code, not a file checksum.
A flash array contains 256 rows of 256 main-flash bytes for this profile.
Each record also supplies 32 bytes for the auxiliary flash area, which the application uses for configuration.
The [Cypress host parser] and [PSoC register definitions] establish the field layout and row geometry.

**Verified:** The file contains 209,463 bytes and 356 lines, with LF terminators.
Its SHA-256 is `7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24`.
All seven source files and four derived files match the sizes and hashes in `docs/firmware/provenance.json`.
Hash agreement establishes artifact identity, not firmware correctness.

**Verified:** Independent reconstruction matches `/tmp/apogee-fw/flash.bin` and `/tmp/apogee-fw/config.bin` byte for byte.
The reconstruction includes artificial bytes where the vendor file supplies no row.
Those derived files are analysis inputs, not flashable device backups.

Addresses below are PSoC CPU addresses unless the column says CYACD or derived offset.
Intervals with two endpoints are inclusive unless explicitly marked exclusive.
CYACD offsets count raw ASCII bytes, not decoded bytes.
`flash.bin` offset equals main-flash address minus `0x10000`.
`config.bin` offset equals auxiliary address minus `0x48000000`.

Evidence tags mean:

- **Verified:** Direct file measurement or an explicit statement in the cited primary source.
- **Inferred:** An interpretation supported by the stated bytes and source, without the missing device state.
- **Unknown:** The available artifacts do not establish the answer.

## Reference: header and records

**Verified:** CYACD bytes `0x00–0x0B` are `2E12F0690000`, followed by LF at `0x0C`.
The [Cypress host parser], lines 76–100, decodes these fields.

| CYACD ASCII offset | Decoded width | Field | Value | Evidence |
|---|---:|---|---|---|
| `0x00` | 4 | Silicon ID, most-significant byte first | `0x2E12F069` | Verified, header bytes |
| `0x08` | 1 | Silicon revision | `0` | Verified, header bytes |
| `0x0A` | 1 | Packet checksum type | `0`, additive sum | Verified, header and [checksum enum], lines 60–65 |

**Verified:** The header contains no header-checksum field.
Its last byte selects a checksum algorithm for bootloader communication packets.
It is not an integrity byte for the header or application.
The [packet checksum implementation], lines 14–50, uses a 16-bit additive checksum for type zero.
No communication packet occurs in this CYACD file.

**Verified:** Each subsequent line has this shape, as defined by the [Cypress host parser], lines 103–137:

```text
: AA RRRR LLLL [data] CC
```

Spaces above separate fields only.
The actual file contains no spaces.
`AA` is the array, `RRRR` is the row within that array, and `LLLL` is the payload byte count.
The two 16-bit fields use most-significant byte first.
`CC` is the record checksum.

| Decoded record offset, after colon | Width | Meaning | Vendor value |
|---|---:|---|---|
| `0` | 1 | Array | 1, 2, or 3 |
| `1` | 2 | Row within array | `0–255` |
| `3` | 2 | Payload length | `0x0120`, or 288 bytes |
| `5` | 256 | Main flash | Code, data, or metadata |
| `261` | 32 | Auxiliary flash | Configuration bytes |
| `293` | 1 | Record checksum | Per-row additive complement |

**Verified:** All 355 records contain 294 decoded bytes, 589 ASCII characters, and one LF.
All array/row pairs are unique and strictly ordered.
For every record, `sum(decoded_record) & 0xFF == 0`.
The checksum excludes the colon, ASCII encoding, and line terminator.
It includes array, both row bytes, both length bytes, and all 288 payload bytes.
The final record has checksum `0xF6`, not the application's checksum `0x73`.

**Verified:** Main-flash address is `array * 0x10000 + row * 0x100`.
Auxiliary address is `0x48000000 + (array * 256 + row) * 32`.
The [PSoC register definitions], lines 5015–5018 and 5331–5337, define this geometry.
The [Cypress bootloader source], lines 1909–1914, applies the auxiliary formula.

## Reference: exact coverage

| Array and row | Record count | Main-flash interval | Auxiliary interval | First CYACD line and offset | Status |
|---|---:|---|---|---|---|
| 1, rows 0–255 | 256 | `0x10000–0x1FFFF` | `0x48002000–0x48003FFF` | Line 2, `0x0000D` | Verified |
| 2, rows 0–97 | 98 | `0x20000–0x261FF` | `0x48004000–0x48004C3F` | Line 258, `0x24E0D` | Verified |
| 3, row 255 | 1 | `0x3FF00–0x3FFFF` | `0x48007FE0–0x48007FFF` | Line 356, `0x32FE9` | Verified |

**Verified:** The file supplies 90,880 main-flash bytes and 11,360 auxiliary bytes.
The application occupies 354 rows, or 90,624 main-flash bytes plus 11,328 auxiliary bytes.
The metadata occupies the remaining record.
Its first 192 main-flash bytes and all 32 auxiliary bytes are zero.
The last application record starts at CYACD `0x32D9B`, line 355.

**Verified:** The first 16 main-flash bytes, at CYACD `0x18`, are:

```text
00 80 00 20 11 00 01 00 69 19 02 00 69 19 02 00
```

These decode to initial stack pointer `0x20008000`, reset vector `0x10011`, and two vectors of `0x21969`.
The reset vector agrees with the metadata entry point.
Agreement does not establish executable correctness.

## Reference: metadata

**Verified:** The 64-byte application metadata starts at main flash `0x3FFC0`, derived offset `0x2FFC0`, and CYACD ASCII offset `0x33174`.
The [Bootloadable metadata definitions], lines 134–166, define the classic layout.
The [Cypress bootloader source], lines 2855–2927, defines field widths.
All multi-byte values below use least-significant byte first.

```text
73 11 00 01 00 FF 00 00 00 00 62 01 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

| Metadata offset | Main-flash address | CYACD ASCII offset | Width | Content and interpretation | Status |
|---|---|---|---:|---|---|
| `0x00` | `0x3FFC0` | `0x33174` | 1 | Application checksum `0x73` | Verified |
| `0x01` | `0x3FFC1` | `0x33176` | 4 | Entry point `0x10011`, Thumb code at `0x10010` | Verified |
| `0x05` | `0x3FFC5` | `0x3317E` | 2 | Last bootloader row `255`, global row index | Verified |
| `0x07` | `0x3FFC7` | `0x33182` | 2 | Zero, unused gap in classic layout | Verified bytes, inferred purpose |
| `0x09` | `0x3FFC9` | `0x33186` | 4 | Application main-flash length `0x16200` | Verified |
| `0x0D` | `0x3FFCD` | `0x3318E` | 1 | Run-type byte `0` | Verified bytes and classic field name |
| `0x0E` | `0x3FFCE` | `0x33190` | 2 | Zero gap | Verified bytes, unknown vendor use |
| `0x10` | `0x3FFD0` | `0x33194` | 1 | Active byte `0` | Verified |
| `0x11` | `0x3FFD1` | `0x33196` | 1 | Verified byte `0` | Verified |
| `0x12` | `0x3FFD2` | `0x33198` | 2 | Bootloader version `0` | Verified |
| `0x14` | `0x3FFD4` | `0x3319C` | 2 | Application ID `0` | Verified |
| `0x16` | `0x3FFD6` | `0x331A0` | 2 | Application version `0` | Verified |
| `0x18` | `0x3FFD8` | `0x331A4` | 4 | Customer ID `0` | Verified |
| `0x1C–0x3F` | `0x3FFDC–0x3FFFF` | `0x331AC–0x331F3` | 36 | All zero | Verified bytes, unknown vendor use |

**Verified:** Later [Cypress private definitions], lines 224–225, assign optional copy and user fields at offsets `0x1C` and `0x20`.
**Unknown:** Their applicability to this absent Apogee bootloader.
The inspector preserves the complete metadata bytes instead of imposing those later meanings.

**Unknown:** Vendor behavior for the run, active, and verified bytes.
Zero values do not establish an inactive or unbootable application.
The version fields also do not encode the reported product version here.
The file contains zeros at those offsets, not version `1.5.3`.

## Explanation: three checksums and hardware ECC

**Verified:** The record checksum protects each record's decoded address, length, main-flash bytes, and auxiliary bytes with an 8-bit sum.
The header selects a separate 16-bit communication-packet checksum.
The metadata contains a third checksum over application memory, not over CYACD text.

**Verified:** [Cypress private definitions], lines 114–116, define the application start as `(last_bootloader_row + 1) * flash_row_size`.
Here that is `(255 + 1) * 256 = 0x10000`.
The metadata length gives exclusive end `0x26200`.

**Verified:** [Cypress bootloader source], lines 1380–1419, adds application main-flash bytes and, with ECC disabled, the corresponding auxiliary bytes.
It then takes the low-byte two's complement.
For this vendor file:

```text
main flash: [0x00010000, 0x00026200), 90624 bytes, sum modulo 256 = 0x2A
auxiliary:  [0x48002000, 0x48004C40), 11328 bytes, sum modulo 256 = 0x63
app checksum = -(0x2A + 0x63) & 0xFF = 0x73
flash-only checksum = -0x2A & 0xFF = 0xD6, which does not match
```

**Verified:** The byte measurement matches the metadata checksum exactly, with no absent rows or artificial fill inside either interval.
The algorithm includes all 32 auxiliary bytes of each application row, including zero bytes.
It excludes array zero, unused flash after `0x261FF`, and the entire metadata row.
It also excludes the metadata row's auxiliary bytes.

**Verified:** The reference source has a special case when application data ends exactly at the metadata base.
It includes the final row's full auxiliary area in that case, despite the shorter main-flash interval.
This vendor file does not use that case.
The inspector rejects non-row-aligned lengths instead of implementing an unneeded profile.

**Inferred:** This image expects auxiliary flash as configuration storage, with hardware ECC disabled.
The evidence combines the 288-byte records, checksum agreement, and configuration reads in application function `0x21CCC`.
That function passes `0x48002000` and `0x480020B0` to the register-table loader at `0x21AD4`.
It also copies pin data from `0x48003248–0x4800329F`.
Derived offsets are `0x11CCC`, `0x11AD4`, and configuration offsets `0x2000`, `0x20B0`, `0x3248–0x329F`.
The [generated configuration source], lines 168–181, shows the same kind of auxiliary-memory tables.

**Verified:** The [CY8C52LP datasheet], printed page 21, Table 5-3, assigns hardware ECC control to the `ECCEN` nonvolatile latch.
`ECCEN=0` selects configuration/data storage, while `ECCEN=1` enables ECC and is the factory default.
The record and application checksums do not set this latch.

**Unknown:** The actual hardware ECC mode, protection bits, and bootloader build configuration.
The file contains no device-state observation or device-configuration latch record.
The inspector verifies auxiliary-byte inclusion, not ECC parity, ECC enable state, or actual bootloader acceptance.
The register writes to `CACHE_CC_CTL` at function `0x21CCC` do not by themselves establish the hardware ECC mode.

**Verified:** The reference bootloader also rejects an application whose main-flash bytes are all zero or `0xFF`.
It can skip the checksum if its optional fast-validation path sees the verified flag.
These are reference-source behaviors, not verified facts about the absent Apogee bootloader.
The inspector always computes the checksum, independent of that flag.

## Reference: silicon identity and absent content

**Verified:** Header bytes name silicon ID `0x2E12F069` and revision zero.
An independent Cypress-generated [part fitter header], lines 2991–2992, contains the same ID and the PSoC 5 family selection.
The same project's [part project file], line 2678, selects `CY8C5268AXI-LP047`.

**Verified:** The [CY8C52LP datasheet], printed page 105, Table 12-1, explicitly maps JTAG ID `0x2E12F069` to `CY8C5268AXI-LP047`.
It lists 100-TQFP packaging, 67 MHz CPU speed, 256 KB flash, 64 KB static RAM, and 2 KB EEPROM.
EEPROM is electrically erasable programmable read-only memory, separate from main flash.
The table identifies a Cortex-M3 CPU.
The official PDF is 5,627,065 bytes, with SHA-256 `87963dfadfc60af9587319133945cbfde2b60f191fcd3d219e9fa80e2b7d69ce`.
Its document number is `001-84933`, revision `*P`.

**Inferred:** This CYACD targets `CY8C5268AXI-LP047`.
**Unknown:** The installed board's physical part number and revision.
A target ID in a file is not a chip readback or package photograph.
Do not substitute a different `CY8C58xx` order code without evidence.

**Verified:** The documented 256 KiB target agrees with the metadata location and four-array geometry.
Evidence: CYACD array 3 row 255, metadata at `0x3FFC0`, and the [Cypress private definitions], lines 194–204.
This describes the image target, not a measurement of the attached chip.

| Absent content | Evidence | Consequence and status |
|---|---|---|
| Array 0, main flash `0x00000–0x0FFFF` | No array-zero record, metadata last bootloader row `0xFF` | Verified absence. Bootloader reservation inferred. Actual bootloader contents unknown |
| Array-zero auxiliary `0x48000000–0x48001FFF` | No array-zero record | Verified absence. Derived zero bytes are artificial |
| Array 2 rows 98–255, array 3 rows 0–254 | Record inventory | Verified absence. Main flash `0x26200–0x3FEFF` and auxiliary `0x48004C40–0x48007FDF` are not captured |
| Second application metadata row | No array 3 row 254 | Verified absence. Dual-image capability of the resident bootloader unknown |
| Dedicated flash protection and device-security records | Every record addresses main flash arrays 1–3 with a 288-byte payload | Verified absence. Protection, debug access, and erase policy unknown |
| Device-configuration nonvolatile latches and write-once security latch | No record outside main-flash arrays. [CY8C52LP datasheet], printed pages 21 and 59, defines these separate controls | Verified absence. `ECCEN` and irreversible security state unknown |
| Embedded EEPROM contents | No array IDs `0x40–0x7F`, as defined in [Cypress private definitions], lines 134–145 | Verified absence. Persistent user settings are not backed up |
| Factory trim and hidden device flash | No record represents the `0x49000000` region from [PSoC register definitions], lines 5019–5023 | Verified absence. Factory state unknown |
| External flash contents | No external-memory record or external address field | Verified container limitation. External device state unknown |
| Authenticity signature | No signature field in the decoded header or record structure | Verified format fact. No authenticity guarantee. Embedded code constants require separate analysis |

**Verified:** The updater supplies separate `E2FPGA.bin` and `EnsembleResourceData.bin` files.
Their lengths are 1,813,864 and 230,036 bytes, respectively, and their hashes match `docs/firmware/provenance.json`.
They are not CYACD records and the inspector does not validate their contents.
**Unknown:** Whether those files plus this application reproduce all external flash, calibration, or persistent device state.

## Explanation: existing extractor assumptions

**Verified:** `scripts/ghidra/psoc-images.py` and `scripts/psoc-firmware.py` read rows with the inspector's `parse`.
A bad header, hex, row length, row checksum, array, geometry, or row order stops the extraction.
The extractors do not run the metadata and coverage checks of `inspect`.

**Verified:** Its geometry matches this specific vendor file.
Its main-flash image starts at `0x10000`, not zero.
Its configuration image starts at global row zero, not at application row 256.
The independent baseline test checks both complete derived files.

| Derived interval | Extractor value | Meaning |
|---|---|---|
| `flash.bin[0x16200:0x2FF00]` | 105,728 bytes of `0xFF` | Verified synthetic substitution, not observed erased flash |
| `config.bin[0:0x2000]` | 8,192 zero bytes | Verified synthetic substitution, absent bootloader configuration |
| `config.bin[0x4C40:0x7FE0]` | 13,216 zero bytes | Verified synthetic substitution, absent rows |

**Verified:** The tests keep their own row decoder, independent of the shared parser.
A minimal integration can gate extraction on inspector success for the exact same input file.
That gate adds the metadata and coverage checks only.
It does not authorize device access or convert derived files into flashable images.
No serializer or round-trip tool was needed.
A serialization round trip could prove byte preservation only, not firmware correctness.

## Procedure: offline inspection and tests

Run the inspector against the vendor source:

```sh
python3 -B scripts/firmware/image-format-inspect.py \
  '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsemblePSoC.cyacd'
```

Run the complete image-format test suite:

```sh
python3 -B scripts/firmware/image-format-test.py -v
```

**Verified:** All 20 tests pass, including vendor-file and derived-baseline checks.
The initial test run failed because the inspector module did not exist.
The implementation then passed the tests.
Additional vendor corruption and sparse-baseline tests also pass.
No hardware test, updater execution, or device call occurred.

**Verified:** Tests cover bad hex, whitespace, header mismatch, unsupported geometry, length errors, duplicate rows, row order, absent rows, and metadata bounds.
They also cover flash and auxiliary corruption after record-checksum repair, including the final application row.
A balanced two-byte corruption deliberately passes both sums.
A metadata verified-flag change also leaves the application checksum unchanged.
Those tests demonstrate integrity limits, not firmware correctness.

**Verified:** The inspector emits JSON and exits with status 2 on an unsupported or inconsistent input.
It supports only the observed silicon header, fixed origin `0x10000`, ascending unique rows, and 256+32-byte payloads.
It requires the exact application row coverage that metadata describes, plus the final metadata row.
It rejects unaligned lengths and applications that enter the metadata row.
It checks the Thumb entry range and reset-vector agreement, but does not execute code.
It reports metadata bytes without certification of their semantics.
It has no device interface, image writer, serializer, or network operation.
Vendor-specific tests skip when the vendor file is absent.
The baseline test skips when either derived binary is absent.

**Proposed integration, not applied:** Add the inspector command before the extractor invocation, joined with `&&`.
Pass the same source pathname to both commands.
Treat extraction output as disassembly input only.

## Safety notes

- Do not flash `flash.bin` or `config.bin`. Their artificial bytes can overwrite unknown device state.
- Preserve the resident bootloader. Its bytes, recovery interface, and protection policy remain unknown.
- Preserve auxiliary bytes with application bytes. Their register tables control peripheral and pin configuration.
- Do not treat checksum agreement as proof of bootability, authenticity, or hardware safety.
- Do not reuse the additive checksum as a cryptographic integrity check. Balanced changes evade it.
- Do not alter metadata flags to bypass verification. Their resident-bootloader behavior is unknown.
- Do not infer ECC enable state from the file checksum. The physical mode requires separate evidence.

These constraints follow from the absent ranges, reference checksum algorithm, and configuration loader at `0x21CCC`.

## Open questions and proposed tests

| Question | Status and next evidence |
|---|---|
| Resident bootloader algorithm, version, accepted arrays, fast-validation policy, and security key | Unknown. Obtain an existing factory bootloader artifact through a non-device source |
| Installed part number and physical revision | Unknown. Official target-ID association is verified. Obtain an existing board photograph or factory bill of materials |
| Physical ECC mode and protection/security state | Unknown. Obtain a factory programming specification or an existing complete backup |
| Metadata run-type and optional fields in this exact component version | Unknown. Obtain the original Creator project or bootloader source |
| Firmware correctness after a modification | Unknown. Check code, data dependencies, configuration tables, and hardware effects independently of these sums |
| Complete EEPROM, external flash, calibration, and hidden flash | Unknown. Separate artifacts are required. The updater bundle is not a full unit backup |

No device test is proposed by this report.
The two offline commands above require no hardware access and do not change source artifacts.

## Primary source references

The Cypress host and component sources below retain Cypress copyright headers.
Some survive in third-party repositories, but their implementation text is the primary evidence.
Those component builds are references, not the recovered Apogee bootloader.
All source-code revisions below are fixed.
The PDF identity is fixed by its revision and SHA-256 above.

- [CY8C52LP datasheet]: flash, ECC, protection, and EEPROM, printed pages 20–21. Security latch, page 59. Part-ID table, page 105.
- [Cypress host parser]: header and row fields, lines 76–137.
- [Checksum enum]: packet algorithm selector, lines 60–65.
- [Packet checksum implementation]: 16-bit packet algorithms, lines 14–50.
- [Bootloadable metadata definitions]: classic field offsets, lines 134–166.
- [Cypress bootloader source]: application checksum, lines 1349–1433, and metadata field widths, lines 2855–2927.
- [Cypress private definitions]: application origin, EEPROM arrays, metadata address and fields, lines 114–145 and 194–225.
- [PSoC register definitions]: auxiliary and hidden regions, lines 5015–5023, and row geometry, lines 5331–5337.
- [Generated configuration source]: auxiliary-memory tables, lines 168–181.
- [Part fitter header]: silicon ID and family, lines 2991–2992.
- [Part project file]: selected order code, line 2678.

[CY8C52LP datasheet]: https://www.infineon.com/assets/row/public/documents/30/49/infineon-psoc5lp-cy8c52lp-datasheet-datasheet-en.pdf
[Cypress host parser]: https://raw.githubusercontent.com/clementleger/cypress_linux_tools/da19a9bc2f65d1641305e4d729a6b7f7a39c01a3/cyhostboot/host_bootloader_src/cybtldr_parse.c
[checksum enum]: https://raw.githubusercontent.com/clementleger/cypress_linux_tools/da19a9bc2f65d1641305e4d729a6b7f7a39c01a3/cyhostboot/host_bootloader_src/cybtldr_command.h
[packet checksum implementation]: https://raw.githubusercontent.com/clementleger/cypress_linux_tools/da19a9bc2f65d1641305e4d729a6b7f7a39c01a3/cyhostboot/host_bootloader_src/cybtldr_command.c
[Bootloadable metadata definitions]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopeKitProg/Scope_KitProg.cydsn/Generated_Source/PSoC5/Bootloadable.h
[Cypress bootloader source]: https://raw.githubusercontent.com/dmaone/CommonSense/55c592ee604eede980094b66533ff8b438f8b0d8/Bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c
[Cypress private definitions]: https://raw.githubusercontent.com/dmaone/CommonSense/55c592ee604eede980094b66533ff8b438f8b0d8/Bootloader.cydsn/Generated_Source/PSoC5/Bootloader_PVT.h
[PSoC register definitions]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopeKitProg/Scope_KitProg.cydsn/Generated_Source/PSoC5/cydevice_trm.h
[generated configuration source]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopeKitProg/Scope_KitProg.cydsn/Generated_Source/PSoC5/cyfitter_cfg.c
[part fitter header]: https://raw.githubusercontent.com/eltradec/SCSI2SD-Proc/bac90efb2aaafa9168b5520a62ed180cc04470ef/creator/SCSI2SD.cydsn/Generated_Source/PSoC5/cyfitter.h
[part project file]: https://raw.githubusercontent.com/eltradec/SCSI2SD-Proc/bac90efb2aaafa9168b5520a62ed180cc04470ef/creator/SCSI2SD.cydsn/SCSI2SD.cyprj
