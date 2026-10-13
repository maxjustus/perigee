# PSoC update and recovery boundaries

Static analysis proves several update hazards, but does not prove recovery after loss of an FPGA image or PSoC application.

## Evidence and scope

**Verified** means direct application instructions or supplied file bytes. **Inferred** means a conclusion from cited evidence. **Unknown** means the inputs do not establish the behavior.

PSoC means the Cypress microcontroller. FPGA means the programmable logic device. EMIF means the PSoC external memory interface.

CRC means cyclic redundancy check. EEPROM means the separate nonvolatile byte store. UDB means a PSoC programmable digital block.

Addresses without a prefix identify PSoC instructions or data. FPGA offsets identify bytes relative to PSoC address `0x60800000`.

External addresses identify values sent to the FPGA flash bridge, not independently verified physical chip offsets.

Primary evidence: `/tmp/apogee-fw/flash.bin`, `/tmp/apogee-fw/config.bin`, and the updater resources below. The analysis cross-checks `decompiled.c` against Thumb instructions.

| Input | Verified size | SHA-256 |
|---|---:|---|
| `EnsemblePSoC.cyacd` | 209463 bytes | `7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24` |
| `E2FPGA.bin` | 1813864 bytes | `b3ef52ae2d1e255307e286d92f2dc92f8dccc06f0f58f7eb1c55a6cbbc4ffdf2` |
| `EnsembleResourceData.bin` | 230036 bytes | `3febcf6f14123ca9767fe651a87fc6fd5ba875dbe52fadf0b3160ce73bdb290b` |

The source directory is `/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources`.

**Verified:** The CYACD records contain array 1 rows 0–255, array 2 rows 0–97, and array 3 row 255. No array 0 record exists.

**Verified:** Application data spans `0x10000–0x261FF`. The metadata row is `0x3FF00–0x3FFFF`. These addresses follow the CYACD array and row fields.

**Unknown:** Array 0 contents, protection, entry conditions, application validation, and recovery transport. Absence from CYACD does not establish bootloader survival or accessibility.

## Application update protocol

### Dispatch and state

**Verified:** `0x16228` dispatches all four commands. The message has command at `+8`, p1 at `+9`, p2 at `+10`, and data at `+11`.

| Command | Verified handler and arguments | Effect |
|---|---|---|
| `0x60` | `0x16F2A–0x16F30` calls `0x17FB4(data[0])` | Select update mode or request bootloader |
| `0x61` | `0x16F3C` calls `0x18198()` | Finalize current mode. Ignores command arguments |
| `0x62` | `0x16F48–0x16F56` calls `0x18098(data, p1)` | Append p1 bytes, not the parser data length |
| `0x63` | `0x16F62–0x16F68` calls `0x18344(data[0])` | Restore output controls or request deferred restart |

| RAM address | Verified role | Evidence |
|---|---|---|
| `0x1FFF8F24` | Mode byte. 0 bootloader request, 1 resources, 2 FPGA, 3 inactive | `0x17F90`, `0x17FB4`, `0x1836C` |
| `0x1FFF8F28` | Next external address, 32 bits | `0x17FF8`, `0x18144–0x1814E` |
| `0x1FFF8F2C` | Buffered byte count, 32 bits | `0x180A2–0x180A6`, `0x180F0–0x180F8` |
| `0x1FFF8F30` | Update error, 32 bits | `0x17F90`, `0x18198` |
| `0x1FFF9170` | 256-byte update buffer | Literal `0x18194`, writes at `0x180EC–0x180EE` |
| `0x1FFF8EF8`, `0x1FFF8EFC` | Separate bridge error fields | `0x123E0`, `0x12444`, `0x124DC` |

**Verified:** `0x17F90` initializes mode 3, count 0, and error 0. It does not explicitly initialize the address or buffer.

**Verified:** `0x21970` zeroes the uninitialized RAM region at startup. Update progress therefore does not persist across an application restart.

### Mode entry

| Mode | Verified action | Evidence |
|---|---|---|
| 0 | Write the EEPROM flag, write FPGA `0x2D=0`, then request bootloader reset | `0x17FCC–0x17FE2` |
| 1 | Set address `0x380000`, clear count/error, mute outputs, zero stored resource version | `0x17FE8–0x18030` |
| 2 | Set address `0x1C0000`, clear count/error, mute outputs, zero stored FPGA version | `0x18032–0x1807A` |
| Other | Set mode 3 and error 1 | `0x1807C–0x18086` |

**Verified:** Modes 1 and 2 do not write FPGA `0x2D`. Only mode 0 writes zero there (`0x17FB4`).

**Verified:** The mute helper acts only if `0x1FFF912F` is nonzero. It writes `0xFF` to volume controls and calls two mute helpers (`0x14F54`, `0x15288`).

**Unknown:** This conditional path does not prove electrical silence under every clock, power, or FPGA fault.

### Packet append and finalization

**Verified:** `0x18098` accepts data only while update error equals zero. It copies enough bytes to fill the current 256-byte buffer.

**Verified:** Before each full-page request, `0x1836C` checks the current address. At each 64-KiB boundary, `0x18130` calls the erase wrapper.

**Verified:** `0x18140` requests a 256-byte program. The handler advances the address by 256 and buffers the remainder (`0x18144–0x18186`).

**Verified:** The handler has no packet index, packet CRC, sequence check, duplicate check, or expected total size (`0x18098–0x1818C`).

**Inferred:** A duplicate packet shifts subsequent bytes. An omitted packet closes the gap without detection in this handler.

**Verified:** `0x18198` first computes `next_address - base`. It rejects zero before it considers the buffered tail (`0x181D8–0x181E6`).

**Inferred:** An update with fewer than 256 bytes fails with error 4 and does not program its tail.

**Verified:** Finalization validates the next address even without a tail (`0x181E8–0x181F0`). It then programs a nonempty tail and reads the received extent back.

**Inferred:** An exact partition-size update programs its final page, then returns error 2 because the next address equals the exclusive end.

**Verified:** Finalization computes an eight-bit CRC over readback bytes. It neither receives nor compares an expected CRC (`0x18234–0x182A4`).

**Verified:** Report `0x61` contains two bytes: update error, then CRC. Its table descriptor at `0x25FA4` is `61 02 00 00 00 00 00 01`.

**Verified:** Mode 1 reloads the resource header even after an update error. It then stores the CRC and updates resource version state (`0x182DE–0x18320`).

**Verified:** Finalization sets mode 3 and clears the update error. It does not clear the address or every possible buffered count (`0x18324–0x1832E`).

| Report error | Verified meaning | Evidence |
|---:|---|---|
| 0 | No error in the update state machine. Not proof of correct flash contents | `0x18198` |
| 1 | Unsupported mode value | `0x1807C–0x18086` |
| 2 | Current address outside the selected interval | `0x1810E–0x1811C`, `0x182A8–0x182AC` |
| 3 | Finalize in inactive mode 3 | `0x181C8–0x181D4` |
| 4 | No full page before finalization | `0x181D8–0x181E4` |

## External flash reference

### Address map and erase schedule

| Interval | Classification | Evidence and limit |
|---|---|---|
| `0x000000–0x1BFFFF` | **Unknown:** contents and boot role | Neither update mode selects this interval (`0x1836C`, `0x183F4`) |
| `0x1C0000–0x37FFFF` | **Verified:** mode 2 interval, size `0x1C0000` | Unsigned lower/upper checks at `0x183C4–0x183D6` |
| `0x380000–0x7FFFFF` | **Verified:** mode 1 interval, size `0x480000` | Unsigned lower/upper checks at `0x1839A–0x183AC` |
| `0x800000` and above | **Verified:** not accepted by these update modes | `0x1836C` |

**Inferred:** Mode 2 stores FPGA firmware, because mode entry clears the FPGA version property (`0x18056–0x18076`).

**Verified:** Resource reads add `0x380000` to resource-relative offsets (`0x1C49C`). This independently establishes the resource base.

**Verified:** The application issues erase requests at addresses with low 16 bits zero (`0x18124–0x18130`, `0x1820C–0x18218`).

**Inferred:** The intended erase unit is 64 KiB. Physical sector geometry remains unknown without the FPGA bridge implementation and flash identification.

| Supplied file | Verified file extent at selected base | Inferred erase request schedule for that complete file |
|---|---|---|
| FPGA | `0x1C0000–0x37AD67`, 7085 full pages plus 104 bytes | 28 requests, `0x1C0000 + n*0x10000`, n=0…27 |
| Resources | `0x380000–0x3B8293`, 898 full pages plus 148 bytes | Four requests: `0x380000`, `0x390000`, `0x3A0000`, `0x3B0000` |

The file extents follow file sizes. The request schedules follow `0x18098` and `0x18198`, not a device trace.

**Unknown:** The application does not identify the physical flash part, actual capacity, physical opcodes, or erase protection.

### FPGA bridge registers

| FPGA offset | Verified application use | Evidence |
|---|---|---|
| `0x2D` | Write 1 after startup readiness call. Write 0 before bootloader reset | `0x1F92A`, `0x17FD4` |
| `0x2E` bit 0 | Poll as busy | `0x12382–0x123C0` |
| `0x2E` write `0x02` | Erase request | `0x1240A–0x1240E` |
| `0x2E` write `0x0A` | Program request | `0x124A4–0x124A8` |
| `0x2E` write `0x12` | Read request | `0x12518–0x1251C`, `0x125B0–0x125B4` |
| `0x2F–0x30` | Read length, little-endian 16 bits | `0x1250C–0x12514`, `0x12658` |
| `0x31–0x33` | Address, low 24 bits, little-endian | `0x12334–0x12356` |
| `0x34` | Write `0x1E` before erase/program, zero after | `0x123FE–0x1242A`, `0x1246E–0x124C4` |
| `0x0C00` onward | Shared transfer buffer. Program copies at most 256 bytes. Read copies at most 1024 bytes | `0x12444`, `0x124DC` |

**Unknown:** `0x02`, `0x0A`, and `0x12` are FPGA command values, not proven serial-flash opcodes. The meaning of `0x34=0x1E` is unknown.

**Verified:** `0x12370` polls every 100 microseconds for up to 20000 delays, approximately two seconds plus software overhead.

**Verified:** Each erase/program/read wrapper records a timeout but continues the operation. None returns a result to the update handler (`0x123E0`, `0x12444`, `0x124DC`).

**Verified:** A program pre-timeout still leads to a program request (`0x12458–0x124A8`). A read post-timeout still copies the buffer (`0x12526–0x1255C`).

**Verified:** These wrappers set `0x1FFF8EF8/0x1FFF8EFC`, not `0x1FFF8F30`. Finalization only reports the latter (`0x182C0–0x182C6`).

**Inferred:** Report error 0 can coexist with a bridge timeout. Readback CRC can derive from stale buffer contents.

**Verified:** The program wrapper does not write a length register or clear bytes beyond its input count (`0x12444–0x124CA`).

**Unknown:** Physical program length for a short tail. The FPGA can consume old buffer bytes beyond that tail. The application alone cannot settle this.

**Verified:** The CRC helper `0x12570` stops on timeout and sets CRC zero. Finalization instead uses `0x124DC`, which continues after timeout.

## Resource storage and validity

### Header and table

All fields below are **Verified** from `EnsembleResourceData.bin` offsets and `0x1C4F4–0x1C5A4`.

| Resource-relative offset | Size | Field | Supplied value |
|---|---:|---|---:|
| `0x00` | 2 | Magic, little-endian | `0x4642`, bytes `42 46` |
| `0x02` | 2 | Format accepted by parser | 3 |
| `0x04` | 2 | Version | 6 |
| `0x06` | 2 | Entry count | 126 |
| `0x08` | 4 | Payload base offset | `0x404` |
| `0x0C` | 4 | Total extent used for whole-file CRC | `0x38294` |
| `0x10` | 1 | Header/table CRC | `0x29` |
| `0x11–0x13` | 3 | Bytes outside the header/table CRC input | Zero |
| `0x14` | 126 × 8 | Resource entries | Ends at `0x404` |

**Verified:** The parser reads the 20-byte header, checks magic and format, then copies every declared entry to RAM (`0x1C504–0x1C576`).

**Verified:** It compares CRC only after those copies (`0x1C578–0x1C580`). The CRC input is header bytes `0x00–0x0F` plus the entry table.

**Verified:** Entry byte 1 supplies width, byte 2 supplies height, and byte 3 supplies another dimension. The entry word at `+4` supplies payload offset.

Evidence: `0x1C63C`, `0x1C6AC`, `0x1C720`, and `0x1C7C0`.

**Verified:** Resource reads compute `0x380000 + payload_base + entry_offset`. The frame variant also adds `frame * width * height * 2` (`0x1C7C0`, `0x1C49C`).

**Verified:** These functions do not check computed extents against the resource partition. The bridge drops address bits above bit 23 (`0x12334`).

**Inferred:** Malformed offsets can select unrelated flash bytes or wrap the 24-bit address. No resource authenticity boundary exists in these functions.

### CRC and unsafe acceptance

**Verified:** `0x218CC` sets CRC zero. `0x218EC` implements CRC-8, polynomial `0x07`, no reflection, and no final XOR.

The instruction sequence at `0x21922–0x21934` applies complement/XOR with `0x7C7F`, then shifts. This is equivalent to polynomial `0x07`.

**Verified:** An independent calculation checked all 256 intermediate XOR states against that sequence. The supplied file CRCs are FPGA `0x2E` and resources `0x1B`.

**Verified:** The resource header/table CRC calculates to `0x29`, which matches file offset `0x10`.

**Verified:** Resource validity at `0x1FFF8F34` means only accepted magic, format, and header/table CRC (`0x1C4F4`). It does not require a payload CRC match.

**Verified:** `0x1C5D4` computes the whole-resource CRC from the header's extent and caches it. It does not compare an expected value.

**Verified:** `0x1C8F8` clears resource validity and reloads the header. It does not clear the cached-CRC flag `0x1FFF8F38`.

**Verified:** The entry destination is `0x1FFF9B78 + 8*i`. No count limit precedes the copy (`0x1C53A–0x1C576`).

**Verified:** Entry index 126 starts at `0x1FFF9F68`, a known resource read-state variable (`0x1C720`, `0x1C8F8`).

**Inferred:** A header count of 127 overwrites that state before CRC validation. Larger counts overwrite further RAM and can fault or corrupt control state.

**Verified:** Startup calls resource reload through `0x189F4`, before the main command loop (`0x1F8FC`).

**Inferred:** A partial or malicious resource image can destabilize the application before the host can repair it. An invalid CRC does not prevent the copies.

## Reset, bootloader, and FPGA startup

### Application request for bootloader

| Stage | Verified application operation | Evidence |
|---|---|---|
| Preserve restart intent | Write `CD AB 01 00` at EEPROM offset `0x7F0` | `0x176F8`, `0x17754` |
| EEPROM physical range | Modify bytes `0x400087F0–0x400087F3` through row `0x7F` | `0x13188`, `0x13258`, `CYREG_EE_DATA_MBASE` |
| Inform FPGA | Write zero to FPGA `0x2D` | `0x17FD0–0x17FD4` |
| Set bootloader request | Write `0x40` to reset status register `0x400046FA` | `0x23300–0x23304` |
| Request CPU reset | Set bit 0 of reset control register `0x400046F6` | `0x23AB8–0x23AC6` |

**Inferred:** `0x232FC` matches the PSoC Bootloadable reset-request pattern. Actual bootloader recognition remains unknown because its instructions are absent.

**Verified:** `0x13188` ignores EEPROM write return codes. The row wrapper `0x23064` has unbounded waits for the system performance controller.

**Inferred:** A fault in EEPROM access can prevent completion of the bootloader request. A failed write can leave the restart-intent flag unchanged.

**Verified:** Application startup accepts EEPROM magic `0xABCD` with a nonzero third byte (`0x17704`). It can clear that byte through `0x17754(0)`.

**Unknown:** Whether the bootloader uses this EEPROM flag. The traced application uses it for its power-state choice (`0x17540`).

### Command 0x63 is not a direct reset

**Verified:** Data 0 calls the output restore helper `0x14F74`. It does not reset the CPU (`0x1835A`).

**Verified:** The display dispatcher also reloads resources for data 0 (`0x19738`, case `0x63`).

**Verified:** Data 1 only sets power-state variable `0x1FFF8F1C` to 5 (`0x18360`, `0x176E0`). Other values do nothing.

**Verified:** An FPGA disconnect event sets `0x1FFF8FD0` when status bit 0 clears (`0x1FD84`). The main loop then calls `0x175C4` (`0x1FF6C`).

**Verified:** In state 5, `0x175C4` writes the EEPROM flag, finishes an active save, clears control bit 2, and enters state 4.

**Verified:** `0x204DC` calls `0x211DC` while `0x211BC` reports an active save.
It does not start a save for dirty state alone.
The separate worker `0x20498` tests dirty age and starts a save through `0x210B0`.
A deferred power-state request therefore does not establish that all changed settings reach EEPROM.

**Verified:** The control clear reaches `CYREG_B0_UDB06_CTL` through `0x11578` and `0x22D5C`.

**Unknown:** The external reset or power effect of that UDB output. Data 1 alone does not prove a CPU restart or FPGA reconfiguration.

### FPGA power-up boundary

**Verified:** Application startup calls `0x11754(1)` after peripheral setup. It does not test the returned result (`0x1F91E–0x1F92A`).

**Verified:** `0x11754` waits for FPGA offset `0x00=0xAB` and bit 1 of offset `0x35` set. It samples offset `0x06` as version state.

**Verified:** The loop permits 10000 attempts. It delays 1000 microseconds only when the signature is not `0xAB` (`0x1179C–0x117DC`).

**Inferred:** Signature present with readiness bit absent exhausts attempts much faster than a ten-second timeout.

**Verified:** On success, the function delays 1200 milliseconds, pulses bit 0 of `CYREG_B0_UDB10_CTL`, then restores FPGA registers `0x08–0x0D`.

Evidence: `0x117EA–0x11832`, `0x1152C`, and `0x22A6C`.

**Verified:** On failure, it records error 4. Startup still writes `FPGA[0x2D]=1` and continues hardware initialization (`0x11836`, `0x1F922–0x1F92C`).

**Unknown:** Configuration source, serial pins, configuration mode, image selector, configuration CRC policy, retry behavior, and fallback logic.

**Inferred:** The application expects useful FPGA logic before its flash bridge can work. This does not identify who loaded that logic.

**Unknown:** The unused lower interval could contain another image, metadata, or unrelated data. Its size alone is not evidence of a golden image.

**Unknown:** No traced path selects the lower interval after a failed update. A golden image, immutable recovery design, or autonomous fallback remains unproven.

### Watchdog and application validity

**Verified:** No decompiled access names `CYREG_PM_WDT_CFG` or `CYREG_PM_WDT_CR`. The image contains neither register address as a 32-bit literal.

The register addresses are `0x40004383` and `0x40004384` in `/tmp/apogee-fw/cydevice_trm.h:177–178`.

**Unknown:** This negative search does not exclude computed accesses, inherited bootloader configuration, UDB logic, or an external watchdog.

**Unknown:** Watchdog reset timing, service policy, brownout thresholds, and power-fail write inhibition. No recovery guarantee follows from a watchdog assumption.

**Verified:** Application startup copies data and zeroes RAM, then enters `0x1F8FC` (`0x21970`). The traced path performs no application-image integrity check.

**Verified:** CYACD row byte sums pass the file checksum test. This establishes file consistency only, not boot acceptance or an on-device flash comparison.

**Verified:** Metadata bytes at `0x3FFC0` begin `73 11 00 01 00 FF 00 00 00 00 62 01`. Other row bytes are zero.

**Unknown:** The actual bootloader's metadata interpretation, valid-image flag transitions, row protection, signature policy, and response to an interrupted metadata write.

## Safety notes

| Adversarial case | Classification and consequence | Evidence |
|---|---|---|
| Power loss after first erase | **Inferred:** The selected image loses old data before a complete replacement exists. No rollback transaction appears in the application path | `0x18130` precedes `0x18140` |
| Power loss during FPGA update | **Unknown:** Next-boot FPGA availability and host access. Neither alternate-image selection nor autonomous recovery is proven | `0x11754`, `0x1836C` |
| Power loss during PSoC update | **Unknown:** Bootloader survival, application rejection, and transport availability | Array 0 absent from CYACD |
| Resource header partly programmed | **Inferred:** Valid magic with a corrupt count can trigger RAM overwrite before CRC rejection | `0x1C504–0x1C580` |
| Erase or program timeout | **Verified:** Wrapper continues and update address advances. Report error 0 remains possible | `0x123E0`, `0x12444`, `0x18144` |
| Wrong but readable firmware | **Verified:** Application returns CRC without expected-value comparison, device identity check, or FPGA image-format validation | `0x18198` |
| Exact partition fill | **Inferred:** All pages can reach flash, then finalization reports address error | `0x18148`, `0x181E8`, `0x1836C` |
| Short update | **Inferred:** Fewer than 256 bytes fail before tail program | `0x181D8–0x181E6` |
| Duplicate or reordered packet | **Inferred:** Silent byte-stream corruption until external CRC comparison | `0x18098` |
| Mode switch mid-transfer | **Verified:** New valid mode resets address, count, and error without rollback | `0x17FB4` |
| Packet count exceeds payload | **Verified:** Handler uses p1 up to 255, independent of copied length. It can read beyond parser-local data | `0x16F50`, `0x180E8–0x180EE` |
| Oversized type-2 payload | **Verified:** Parser skips data copy for length ≥100 but still dispatches the command | `0x153F8`, call `0x155CE` |
| Truncated type-2 record | **Verified:** Parser checks two words exist, not that the declared data extent fits | `0x153F8` |
| Short type-1 update packet | **Inferred:** Only one data byte is initialized, but p1 can request many bytes | `0x154B2`, `0x16F50` |
| Resource offsets exceed partition | **Verified:** Read offsets lack partition validation and truncate to 24 bits | `0x1C49C`, `0x12334` |
| Host disconnect during update | **Inferred:** A partial image remains. No durable page counter or automatic continuation exists in the traced handlers | `0x17F90`, `0x18098` |
| Restore outputs too early | **Verified:** `0x63` data 0 can restore controls without a successful update or CRC comparison | `0x18344`, `0x14F74` |

**Verified:** The p1 byte limits each packet to 255 bytes. Under intact state, this does not itself overflow the 256-byte update buffer (`0x18098`).

**Inferred:** The immediate count mismatch hazard is an out-of-bounds source read and unintended flash bytes, not a proven destination-buffer overflow.

**Inferred:** A CRC-8 match is not authentication. It cannot establish image compatibility, safe pin behavior, or recovery after reset.

## Dependency graph

Arrows mean “requires”. **Verified** edges cite the application. **Inferred** host edges use `NOTES-vendor-driver.md` sections 5–7 and the traced application boundary.

```text
External FPGA-image update
  -> host command route -> active FPGA message interface
  -> PSoC application dispatcher -> update state machine
  -> EMIF -> active FPGA flash bridge -> external flash + stable power

Resource update
  -> same external-update route
  -> safe resource header/table parse after finalization

PSoC application update through the normal application
  -> host command route -> active FPGA message interface
  -> PSoC command 0x60 mode 0 -> EEPROM access -> reset request
  -> bootloader execution [unknown implementation]
  -> bootloader transport through FPGA remote I2C [host evidence, not app proof]
  -> internal flash program and validation [unknown implementation]

Recovery after corrupt PSoC application
  -> bootloader that runs without the application [unknown]
  -> compatible FPGA endpoint and remote I2C [inferred host requirement]
  -> bootloader permits repair [unknown]

Recovery after corrupt FPGA image
  -> a functional FPGA configuration or independent access path [unknown]
  -> normal external-update route, if FPGA and application still function

Recovery after corrupt resources
  -> application reaches command service without unsafe resource parse
  -> active FPGA message interface and flash bridge
  -> resource update route

Bootloader replacement or recovery
  -> independent programmer/debug access and protection policy [unknown]
  -> not established by these application handlers
```

| Dependency edge | Classification and evidence |
|---|---|
| Host message service requires FPGA state and slots | **Verified:** `0x1FEC8`, `0x1FF6C`, `0x11F68`, `0x153F8` |
| Flash update requires active EMIF-accessible FPGA logic | **Verified:** `0x12334–0x12570` |
| Resource service requires accepted table state | **Verified:** `0x1C63C–0x1C86C` |
| Normal PSoC bootloader entry requires application execution | **Verified:** `0x16F30`, `0x17FB4`, `0x232FC` |
| Host bootloader transport requires FPGA endpoint | **Inferred:** Host notes describe BAR0 remote I2C, not an independent cable or programmer |
| Failed FPGA configuration can remove its own repair route | **Inferred:** Both host message slots and flash bridge reside in the FPGA |
| Preserved bootloader alone guarantees recovery | **Unknown:** Requires boot entry, valid configuration, transport, and flash permissions that this image cannot establish |

## Proposed tests

No hardware command is proposed before an independent recovery path and the board connections are known.

| Static test | Exact command or input | Risk and decision |
|---|---|---|
| Reproduce instruction evidence | `python3 scripts/psoc-firmware.py` | No device access. Inspect the cited instruction addresses |
| Recheck supplied image identity | `shasum -a 256 '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/'{EnsemblePSoC.cyacd,E2FPGA.bin,EnsembleResourceData.bin}` | No device access. Stop if hashes differ |
| Check future bootloader evidence | Acquire a static dump of array 0 through an owner-approved process | No acquisition command specified. Hardware reads can change reset or debug state |
| Check future FPGA recovery evidence | Obtain FPGA configuration sources, flash identification, and board reset connections | No device operation. Establish fallback and bridge semantics before any destructive test |

**Unknown:** Safe physical recovery remains the principal blocker. Neither a successful current boot nor the CYACD layout resolves it.
