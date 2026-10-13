# Independent verification of Ensemble recovery

The application confirms the requested update bounds and error defects, but the supplied files do not establish recovery after FPGA or bootloader failure.

## Scope and evidence

This review used static file analysis only. No device access, firmware execution, updater execution, shared Ghidra edits, or commits took place.

The brief, `NOTES-vendor-driver.md`, and `probe-results.md` served as leads, not proof. Claims below derive from vendor bytes and instruction paths.

**Confirmed** means the supplied code or bytes establish the claim. **Refuted** means they contradict it. **Unresolved** means the required evidence is absent.

An **inference** states a consequence of confirmed instructions, not an observed hardware result.

Terms:

- **PSoC**: the device microcontroller. **Application**: its supplied code at address `0x10000` and above.
- **Bootloader**: the separate code that the host expects to accept PSoC updates after reset.
- **FPGA**: the programmable logic that exposes the host registers and the application-side external-flash interface.
- **Host bridge**: the host transport through Thunderbolt, Peripheral Component Interconnect Express (PCIe), and mapped device registers.
- **BAR0**: the first PCIe base-address register window.
- **Flash bridge**: the FPGA interface at PSoC addresses `0x6080002e` to `0x60800034`, plus its buffer at `0x60800c00`.
- **EEPROM**: electrically erasable programmable read-only memory. The application accesses its data at `0x40008000`.
- **Golden fallback**: a separate, usable FPGA recovery image plus an effective selection mechanism after primary-image failure.
- **SWD/JTAG**: Serial Wire Debug and Joint Test Action Group interfaces. Chip support alone does not establish board access or recovery.

### Input identity

The resource directory is `/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources`.

| Input | Independent check |
|---|---|
| `EnsemblePSoC.cyacd` | SHA-256 `7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24`. Header `2E12F0690000`. All 355 row checksums pass. |
| `/tmp/apogee-fw/flash.bin` | SHA-256 `a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8`. Independent extraction from the vendor rows matches every byte. |
| `E2FPGA.bin` | 1,813,864 bytes. SHA-256 `b3ef52ae2d1e255307e286d92f2dc92f8dccc06f0f58f7eb1c55a6cbbc4ffdf2`. |
| `EnsembleResourceData.bin` | 230,036 bytes. SHA-256 `3febcf6f14123ca9767fe651a87fc6fd5ba875dbe52fadf0b3160ce73bdb290b`. |
| Vendor kernel extension | `/Library/Extensions/ApogeeElementEnsemble.kext/Contents/MacOS/ApogeeElementEnsemble`. SHA-256 `4ecc3889b80f27b150307ca2ed299a070e402cb6aff0a8f6234da8e34062eb01`. |
| Vendor audio plugin | `/Library/Audio/Plug-Ins/HAL-disabled/ApogeeElementEnsemble.driver/Contents/MacOS/ApogeeElementEnsemble`. SHA-256 `f23805d2e8a32b04aa135dd392f7f99d1b81751b0365c8f13f5a935147933809`. |

PSoC addresses below are CPU addresses. Their offsets in `flash.bin` equal `address - 0x10000`.
Host addresses identify the kernel extension's x86-64 slice or the audio plugin's arm64 slice, as stated.
Thumb instruction bytes appear in file order. Literal pools and jump tables are data, not instructions.

**Confirmed:** vendor rows cover array 1, rows 0–255, array 2, rows 0–97, and array 3, row 255.
No record supplies array 0. The four initial application vector words are `0x20008000`, `0x00010011`, `0x00021969`, and `0x00021969`.

**Unresolved:** the actual contents of `0x0000–0xffff`. The absent rows do not prove that a device contains an intact bootloader throughout that interval.
Extractor fill bytes do not constitute a device backup.

## Claim verdicts

| Claim | Verdict | Evidence and limit |
|---|---|---|
| Mode 2 accepts addresses in `[0x1c0000,0x380000)` | **Confirmed** | `0x183b6` sets the lower bound. `0x183be` adds `0x1c0000`. Unsigned branches at `0x183cc` and `0x183d6` reject addresses below or at/above the bounds. |
| Mode 1 accepts addresses in `[0x380000,0x800000)` | **Confirmed** | `0x1838c` sets `0x380000`. `0x18394` adds `0x480000`. `0x183a2` and `0x183ac` apply the same comparisons. |
| A golden fallback is proven | **Unresolved, not established** | These bounds exclude the lower `0x1c0000` from this update path. They establish neither its contents nor FPGA selection behavior. |
| A bridge timeout prevents the program operation | **Refuted** | After timeout stores at `0x1245a–0x12464`, execution reaches the buffer copy and opcode write at `0x124a8`. |
| A bridge timeout reaches completion status `0x61` | **Refuted** | Timeout globals are `0x1fff8ef8/0x1fff8efc`. Completion reads the separate status at `0x1fff8f30`, at `0x182c0–0x182c6`. |
| Exact partition fill fails the completion bound check | **Confirmed** | The packet path advances the address by 256 at `0x18148`. Completion checks that next address at `0x181e8`. Equality fails. |
| `0x12444` copies `n` bytes, then emits opcode `0x0a`, without a length write or tail clear | **Confirmed** | The complete path `0x12444–0x124ca` contains only the writes detailed below. It accepts `n <= 256`. |
| The physical flash page size is 256 bytes | **Unresolved** | The application buffer and transfer quantum are 256 bytes. The FPGA implementation and physical flash geometry are not established. |
| Command `0x60`, mode 0, requests a bootloader transition through the cited sequence | **Confirmed as a software request** | `0x17fcc–0x17fe2` writes the EEPROM marker, clears FPGA `0x2d`, and calls the reset sequence. Actual bootloader entry remains unresolved. |
| The EEPROM marker alone proves the bootloader entry rule | **Unresolved** | The application itself reads and clears this marker at `0x17554–0x17566`. The absent bootloader's interpretation is unknown. |
| Command `0x63`, data 1, directly resets the CPU | **Refuted** | `0x18360` calls `0x176e0`. That helper only stores power-state value 5 and returns. |
| Command `0x63`, data 1, schedules power-state 5 | **Confirmed** | Bytes `03 4b 05 22 1a 60` at `0x176e4` store 5 at `0x1fff8f1c`. Board reset effects remain unresolved. |

### Command identity

The dispatcher reads the command at message offset 8, subtracts 1, and loads a Thumb target from the table at `0x1625c`.

| Command | Table address and bytes | Instruction path |
|---|---|---|
| `0x60` | `0x163d8`: `2b 6f 01 00` | `0x16f2c`: `ldrb r3,[r3,#0xb]`. `0x16f30`: `bl 0x17fb4`. |
| `0x61` | `0x163dc`: `3d 6f 01 00` | `0x16f3c`: `bl 0x18198`. |
| `0x62` | `0x163e0`: `49 6f 01 00` | `0x16f50` reads the count from message offset 9. `0x16f56` calls `0x18098` with data at offset 11. |
| `0x63` | `0x163e4`: `63 6f 01 00` | `0x16f64` reads data at offset 11. `0x16f68` calls `0x18344`. |

### Address bounds and exact fill

The update state starts at `0x1fff8f24`:

| Offset | Purpose | Evidence |
|---|---|---|
| `+0` | Mode byte | Loads at `0x1837e–0x18386` |
| `+4` | Current external-flash address | Loads at `0x1839a–0x1839c` |
| `+8` | Buffered byte count | `0x180a2–0x180aa` computes `256 - count` |
| `+12` | Update status | `0x180ac–0x180b2`, `0x182c0–0x182c6` |

Critical Thumb bytes:

```text
0x1838c  4f f4 60 13  mov.w r3,#0x380000
0x18394  03 f5 90 03  add.w r3,r3,#0x480000
0x183a2  07 d3        blo   0x183b4
0x183ac  02 d2        bhs   0x183b4
0x183b6  4f f4 e0 13  mov.w r3,#0x1c0000
0x183be  03 f5 e0 13  add.w r3,r3,#0x1c0000
0x183cc  07 d3        blo   0x183de
0x183d6  02 d2        bhs   0x183de
```

**Confirmed:** `0x183f4` returns `0x1c0000` for mode 2 and `0x380000` otherwise.
The validator accepts only modes 1 and 2, despite that default base.

**Confirmed:** the packet path checks the current address before each full 256-byte program request (`0x1810e`).
It requests erase when the low 16 address bits equal zero (`0x18120–0x18130`).
After the program call, it advances the address by 256 regardless of bridge timeout (`0x18140–0x1814e`).

**Inference, confirmed arithmetic:** an exact fill submits the last block at `upper - 256`, then leaves the next address at `upper`.
Completion rejects that address, sets status 2 at `0x182a8–0x182ac`, and skips the checksum loop.
This is rejection **after** all full-block program requests, not protection before destructive writes.

| Mode | Interval size | Exact-fill next address | Largest length that passes these completion bounds |
|---|---:|---:|---:|
| 2 | `0x1c0000` = 1,835,008 | `0x380000` | `0x1bffff` = 1,835,007 |
| 1 | `0x480000` = 4,718,592 | `0x800000` | `0x47ffff` = 4,718,591 |

These maxima describe address checks, not safe physical write lengths.
Completion also rejects a transfer below 256 bytes: `0x181d8–0x181e6` tests the completed-block length before it adds the residual count.

### Timeout and residual-byte behavior

**Confirmed:** `0x12370` polls flash-bridge register `0x2e`, bit 0.
The loop calls `0x23b18(100)` and increments a counter by 100.
At `0x123be–0x123c0`, it compares against literal `0x001e847f` = 1,999,999 and loops while at or below it.
If bit 0 remains set, the helper returns zero. This proves a counter limit, not a measured wall-clock timeout.

| Path | Timeout stores | Subsequent behavior |
|---|---|---|
| Erase helper `0x123e0` | `(1,1)` at `0x1fff8ef8/0x1fff8efc` | Entry timeout does not prevent opcode 2 at `0x1240e`. |
| Program helper `0x12444` | Entry: `(1,2)`. Completion: `(2,2)` | Entry timeout does not prevent the copy or opcode `0x0a`. |
| Read helper `0x124dc` | Entry: `(1,3)`. Completion: `(2,3)` | It still copies the FPGA buffer at `0x1253a–0x1255c`. |

**Confirmed:** the program helper accepts `n <= 256` at `0x12468–0x1246c`.
Its complete write sequence is:

```text
0x12472          FPGA[0x34] = 0x1e
0x1247a–0x1249c  FPGA[0x0c00 + i] = source[i], for 0 <= i < n
0x124a0          call 0x12334: address bytes to FPGA[0x31..0x33]
0x124a6–0x124a8  FPGA[0x2e] = 0x0a       bytes: 0a 22 1a 70
0x124aa          call 0x12370
0x124c4          FPGA[0x34] = 0
```

The loop's `ldrb/strb` bytes are `1b 78 0b 70` at `0x1248c`.
Its unsigned count comparison is `9a 42 ed d3` at `0x1249a`.
The function neither writes a length nor clears buffer bytes `[n,256)`.
By contrast, the read helper explicitly writes length through `0x12658(0x2f,n)` at `0x12510–0x12514`.

**Unresolved:** whether opcode `0x0a` consumes 256 bytes, an implicit length, a previous length, or another quantity.
Opcode `0x0a` is an FPGA command value. These instructions do not prove a physical serial-flash opcode or page size.
The same limit applies to the erase geometry, despite the application's 64-KiB address cadence.

**Inference:** a fixed-width FPGA program operation can consume stale tail bytes after a short copy.
The application proves the absent tail clear, not that the FPGA actually writes those bytes.

If the host sends the resource files without extra padding, their residual counts are 104 bytes for `E2FPGA.bin` and 148 bytes for `EnsembleResourceData.bin`.
These are file-length calculations, not proof of the host's exact transfer payload.

**Confirmed:** completion calls the read helper at `0x18278`, then the checksum helper at `0x18288`, without a timeout test between them.
It reports the update status from `0x1fff8f30`, not the bridge timeout globals.
The literal at `0x1833c` is `24 8f ff 1f`, the update-state base.
The program helper's literals at `0x124cc/0x124d0` are `f8 8e ff 1f` and `fc 8e ff 1f`.

**Inference:** status zero can coexist with a bridge timeout, and completion can compute a checksum over stale buffer contents.
The completion function returns an eight-bit checksum, but does not compare it with an expected image checksum (`0x18198–0x1833a`).
This review does not assert that the host ignores checksum mismatches.

### Bootloader request versus power-state request

**Confirmed:** mode 0 follows this order:

| Phase | Original instruction evidence |
|---|---|
| Prepare EEPROM marker | `0x17fcc`: `bl 0x176f8`. `0x176fc`: `movs r0,#1`. `0x176fe`: `bl 0x17754`. |
| Form `CD AB 01 00` | `0x1775e–0x17776` sets four bytes. `0x1777c` sets offset `0x7f0`. `0x17782` sets length 4. |
| Submit EEPROM write | `0x17784`: `bl 0x13188`. That helper preserves the other bytes of the 16-byte EEPROM row, then calls `0x23064` at `0x13220`. |
| Clear FPGA flag | `0x17fd0–0x17fd4` writes zero through literal `0x6080002d` at `0x18090`. |
| Set reset status | `0x17fe2`: `bl 0x232fc`. `0x23302–0x23304`: `movs r2,#0x40`, `strb r2,[r3]`. |
| Request CPU reset | `0x23306`: `bl 0x23ab4`. `0x23ac0`: `orr r3,r3,#1`. `0x23ac6`: `strb r3,[r2]`. |

Literal `0x2330c` contains `fa 46 00 40`, address `0x400046fa`.
Literal `0x23ad0` contains `f6 46 00 40`, address `0x400046f6`.
`/tmp/apogee-fw/cydevice_trm.h:534` names the former `CYREG_RESET_SR0`, and line 530 names the latter `CYREG_RESET_CR2`.

**Confirmed:** the EEPROM write wrapper does not check the row-write result before return (`0x13220–0x13224`).
Thus the code proves a write request for `CD AB 01 00`, not successful persistence before reset.

**Confirmed:** the host expects bootloader status 2 after this request.
The audio plugin sends mode 0 at arm64 `0x87c20–0x87c24`, polls status at `0x87c48`, and compares it with 2 at `0x87c5c`.
It opens remote I2C at `0x87c70` only after the status test passes.
I2C means Inter-Integrated Circuit, the serial bus used by this host transport.

**Unresolved:** the bootloader's reset-cause test, marker interpretation, timeout policy, invalid-application policy, and successful entry on an actual board.
The marker is not exclusive evidence of bootloader selection: application startup reads it through `0x17704` and clears it at `0x17566`.

**Confirmed:** command `0x63`, data 1, calls `0x176e0` and returns after the state-5 store.
The event consumer calls `0x175c4` only when its flag passes the test at `0x1ff7a–0x1ff82`.
The state-5 table entry at `0x175e8` contains `09 76 01 00`, target `0x17608`.
That path writes the marker, calls `0x204dc`, calls `0x11578(4,0)`, and stores state 4 (`0x17608–0x1761e`).
It does not directly call the CPU reset helper.

**Unresolved:** whether board circuitry eventually resets the CPU or FPGA after that output change.
The command name `RestartPSocFirmware` does not establish that electrical consequence.

## Recovery dependency graph

Arrows below denote required paths, not verified recovery guarantees.

```text
Host software
  -> usable Thunderbolt/PCIe host bridge
  -> FPGA host register interface
       -> command mailbox -> live PSoC application
                              -> FPGA flash bridge -> external flash
       -> remote I2C engine -> live PSoC bootloader -> PSoC application flash

CPU reset -> bootloader entry/selection -> application or update service
            [device-side code absent]

External-flash contents -> FPGA configuration/selection -> usable FPGA interfaces
                          [behavior not established]

External debug/programmer -> board access, power, reset, security permission
                            -> target repair
                            [board path not established]
```

| Dependency claim | Verdict and evidence |
|---|---|
| The ordinary external update requires a live application | **Confirmed.** The mailbox dispatcher reaches `0x17fb4`, `0x18098`, and `0x18198`. Their flash operations use FPGA addresses, not a direct host flash interface. |
| Host command delivery requires the FPGA register path | **Confirmed.** Kernel x86-64 `0x5bb7–0x5be4` writes command slots at `0x800 + 0x78*slot`. `0x5c27–0x5c48` sets register `0x0c`, bit 6. |
| The remote bootloader transport bypasses ordinary application commands | **Confirmed on the host side.** Plugin arm64 `0x1580`, `0x15c8`, and `0x1608` select miscellaneous requests 1, 2, and 3. |
| The remote bootloader transport bypasses the FPGA | **Refuted for this host implementation.** Kernel x86-64 `0x4262–0x4289` enables register `0x18`. Transfers use `0x3c00` at `0x434a/0x42d9` and trigger `0x18` at `0x5ff1`. |
| Bootloader status proves an independent recovery channel | **Refuted.** Kernel x86-64 `0x3ddc–0x3dee` reads BAR0 `0x68` and extracts bits 7:6. It is another FPGA register observation. |
| The PSoC bootloader can operate without the application | **Unresolved on the device.** The host has a separate protocol: plugin arm64 `0x88280` writes the bootloader packet and `0x882dc` reads its response. The responder code is absent. |
| An intact application alone can repair a nonfunctional FPGA | **Unresolved.** The confirmed external-flash repair path itself uses the FPGA bridge at `0x12444`. Startup probes FPGA `0x0000 == 0xab` and `0x0035` bit 1 at `0x11792–0x117b4`. |
| FPGA failure necessarily halts all application execution | **Refuted as a code claim.** Startup calls `0x11754` at `0x1f91e`, then continues at `0x1f922` without a return-value branch. Usable host communication is a separate question. |
| SWD/JTAG chip support proves board recovery | **Refuted as an inference.** No inspected input establishes accessible board pins, routing, reset authority, voltage, security state, or a complete restore image. |

**Inference:** FPGA damage that removes the host register interface cuts both inspected host update paths.
A healthy Thunderbolt controller or an intact PSoC bootloader does not replace the absent FPGA mailbox or remote I2C engine.

**Inference:** application damage with an intact FPGA preserves a possible host-to-bootloader path, not a proven automatic entry mechanism.
If the bootloader is already active and reachable, the host transport need not invoke the damaged application.
If entry requires command `0x60`, that command depends on the application that failed.

**Inference:** a corrupt bootloader removes another prerequisite even when the FPGA works.
The supplied application image cannot reconstruct absent array-0 bytes.
A direct external-flash programmer also cannot, by itself, restore missing PSoC bootloader code.

### What the absent evidence permits

| Missing evidence | Permitted conclusion | Unsupported conclusion |
|---|---|---|
| Device bootloader bytes | Its policy and recovery entry paths remain unresolved. | Automatic recovery after an invalid application, a button recovery mode, protected bootloader flash, or guaranteed update resume. |
| Lower external-flash contents | This application update path excludes `[0,0x1c0000)`. | A golden image exists there, is valid, or is selected after failure. |
| Decoded FPGA behavior and board configuration | Flash-bridge transaction length, boot selection, and reset effects remain unresolved. | A fixed 256-byte physical page, automatic fallback, or a host recovery bridge that survives a bad FPGA image. |
| Board debug evidence | Direct repair is a candidate that needs separate proof. | Accessible SWD/JTAG, unrestricted reads, nondestructive unlock, or complete restoration through debug. |

The raw `E2FPGA.bin` is present. “Absent bitstream” is therefore inaccurate if it means no vendor FPGA payload exists.
What remains absent from this proof is decoded recovery logic, a validated alternate image, board configuration evidence, and a complete external-flash backup.
Neither absent evidence nor an unexplained lower address range proves that fallback is impossible.

## Safety notes

- Do not treat completion status zero as proof of a successful flash operation. Bridge timeout globals do not reach that status.
- Do not treat exact-fill rejection as a harmless preflight failure. The application already issued the full-block program requests.
- Do not assume short final writes preserve adjacent bytes. The application omits both a length write and a tail clear.
- Do not infer physical erase size from the 64-KiB software cadence. FPGA behavior and chip geometry remain unresolved.
- Do not use the host bootloader transport as an FPGA-independent rescue plan. Both inspected host paths require FPGA registers.
- Do not rely on command `0x63` as a direct CPU reset. Its immediate effect is a state store.
- Do not treat the vendor application file as a full PSoC backup. It contains no array-0 payload.
- Do not attempt debug unlock without a documented protection policy. An unlock that erases flash can destroy the only bootloader copy.

## Static verification and next evidence

The optional verifier checks the vendor hash, row checksums, 45 instruction/data anchors, and two exact-fill calculations.
The byte anchors are consistency checks, not fresh semantic proofs.
The verifier refuses Python optimization before any PASS output because its checks require assertions.
It does not execute firmware, model FPGA behavior, or access a device.

```sh
python3 scripts/firmware/verify-recovery.py
```

The verifier passed all byte groups and both bound calculations.
The wrong-image rejection test, Python syntax check, and Ruff checks also passed.
Capstone decoded the cited Thumb instructions directly from the independently matched application bytes.
`otool` decoded the cited host instructions directly from the installed binaries.

No hardware test is proposed here. No safe board-specific command exists in the inspected evidence for the unresolved recovery paths.

Before a hardware recovery experiment, obtain these prerequisites:

- **Bootloader policy:** obtain authorized bootloader bytes or source, then identify reset entry, application validation, transport setup, and protection rules.
- **FPGA recovery selection:** obtain configuration documentation or decoded logic, plus a complete external-flash image with provenance.
- **Physical flash contract:** identify the flash part and FPGA transaction logic, then establish erase size, program size, length semantics, and timeout behavior.
- **Board debug path:** obtain a schematic or verified pin map, voltage requirements, reset behavior, security state, and a complete restore procedure.

These prerequisites resolve the unproven edges of the dependency graph. They are not instructions to probe or modify the unit.
