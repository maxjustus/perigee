# Ensemble front panel

Verified: EnsembleResourceData.bin contains 126 uncompressed display resources, with 234 image frames, for two 160 × 128 displays.
Evidence: resource offsets `0x00..0x403`, PSoC functions `0x1C720`, `0x1C7C0`, `0x10F78`, and the offline extraction below.

## Scope and evidence

The Ensemble Thunderbolt is the Apogee audio interface under analysis.
PSoC means programmable system-on-chip, the Cypress microcontroller that runs this application.
FPGA means field-programmable gate array, the device that provides the external flash interface.
SPI means Serial Peripheral Interface. I2C means Inter-Integrated Circuit.
OLED means organic light-emitting diode. UI means user interface.
CRC means cyclic redundancy check. RGB565 means a pixel with 5 red, 6 green, and 5 blue bits.

- **Verified** means direct code, byte, or document evidence.
- **Inferred** means a conclusion from the cited evidence, without a physical inspection.
- **Unknown** means the available evidence does not settle the claim.

Function addresses refer to `/tmp/apogee-fw/decompiled.c` and the application in `/tmp/apogee-fw/flash.bin`.
The flash file starts at PSoC address `0x10000`.
Resource offsets refer to the vendor file, not PSoC memory.
External flash addresses use the FPGA flash protocol, not the PSoC CPU address space.

| Input | Verified identity |
|---|---|
| Vendor resource | `/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsembleResourceData.bin`, 230036 bytes |
| Resource SHA-256 | `3febcf6f14123ca9767fe651a87fc6fd5ba875dbe52fadf0b3160ce73bdb290b` |
| PSoC flash SHA-256 | `a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8` |
| Display reference | [SYNCOAM SEPS525, version 0.6](https://www.displayfuture.com/Display/datasheet/controller/SEPS525.pdf), pages 9, 17, 22–27 |
| GPIO reference | [Semtech SX1507/SX1508/SX1509, revision 1](https://cdn.sparkfun.com/datasheets/BreakoutBoards/sx1509.pdf), pages 14, 30–34 |

Verified: this work used static files and offline tests only.
No device access, update, commit, or shared Ghidra edit occurred.

## Corrections to prior claims

| Status | Correction | Evidence |
|---|---|---|
| Verified | The raw prefix is `42 46`, ASCII `BF`. It is not the BMP signature `42 4D`. | Resource `+0x00`, loader `0x1C4F4` compares little-endian `0x4642` |
| Verified | The resource target is not unknown. The PSoC reads it from external flash address `0x380000`. | `0x1C49C` adds `0x380000` before `0x124DC` |
| Verified | Update target 1 selects these resources. Target 2 selects the FPGA image region. | `0x17FB4`, `0x183F4`, `0x18198` |
| Unknown | The letters `BF` do not establish an original format name. | `0x1C4F4` tests only the numeric magic |
| Inferred | The resource uses custom bitmap records, not a standard BMP container. | Twenty-byte header, eight-byte records, exact RGB565 payload extents |
| Verified | Report `0x40`, parameter 3, includes a CRC byte, not a three-component semantic version. | `0x17404`, `0x1C5A4`, `0x1C5D4` |
| Verified | The four local pads use assignment values 0–22. The remote-button enum in `NOTES-vendor-driver.md` does not describe these values. | `0x1A1B0`, `0x1A140`, `0x19D78` |

## Resource format reference

### Header and index

Verified: all multibyte header and index fields use little-endian order.
The pixel bytes use the opposite order.
Evidence: `0x1C4F4`, `0x1C720`, `0x1C7C0`, `0x1C334`, and resource extents.

| Offset | Bytes | Field | Value | Status and evidence |
|---|---:|---|---|---|
| `0x00` | 2 | Magic | `0x4642` | Verified, `0x1C4F4` |
| `0x02` | 2 | Format version | 3 | Verified, `0x1C4F4` |
| `0x04` | 2 | Resource version | 6 | Verified, `0x1C5A4` reads RAM `0x1FFF9B68` |
| `0x06` | 2 | Resource count | 126 | Verified, `0x1C4F4` loop bound |
| `0x08` | 4 | Pixel data offset | `0x404` | Verified, `0x1C720` adds RAM `0x1FFF9B6C` |
| `0x0C` | 4 | Total file bytes | `0x38294` = 230036 | Verified, `0x1C5D4` full-file CRC length |
| `0x10` | 1 | Header/index CRC | `0x29` | Verified, `0x1C4F4`, `0x218EC` |
| `0x11` | 3 | Unused by the loader | Zero | Verified bytes, Unknown original field definition |
| `0x14` | 1008 | 126 index records | Eight bytes each | Verified, `0x1C4F4` |
| `0x404` | 229008 | Pixel payload | No gaps or trailer | Verified, all 126 extent checks |

Verified: record `i` starts at `0x14 + 8*i`.

| Record offset | Bytes | Meaning | Status and evidence |
|---|---:|---|---|
| `+0` | 1 | Kind: 1 for a single image, 2 for a frame array | Inferred semantics from every record and its extent. The draw path does not test this byte. |
| `+1` | 1 | Width in pixels | Verified, `0x1C63C`, `0x1C720` |
| `+2` | 1 | Height in pixels | Verified, `0x1C63C`, `0x1C720` |
| `+3` | 1 | Frame count for kind 2. Zero for kind 1. | Verified extents and `0x1C6AC` consumers at `0x1EBFC` |
| `+4` | 4 | Payload offset relative to `0x404` | Verified, `0x1C720`, `0x1C7C0` |

Verified formulas:

```text
frame_bytes = width * height * 2
frame_start = data_offset + record.offset + frame_index * frame_bytes
record_bytes = frame_bytes * (record.frames if record.kind == 2 else 1)
```

Evidence: `0x1C720`, `0x1C7C0`, and all adjacent record offsets.

Verified: the first record is `01 11 0E 00 00 00 00 00`.
It describes a 17 × 14 image at file offset `0x404`, with 476 bytes.
The next record starts its payload at `0x5E0`, exactly 476 bytes later.

Verified: the image stream has no compression, palette, row padding, or per-frame header.
The PSoC reads at most 64 bytes per resource chunk and sends each byte unchanged to the display.
Evidence: `0x1C86C` and `0x1C334`.

Verified: pixels are row-major RGB565, high byte first.
The controller receives register `0x16 = 0x66` and `0x13 = 0`.
These select horizontal increment, vertical increment, two-byte color, and no red/blue swap.
Evidence: `0x10F78`, SEPS525 pages 9, 23, 25.

### External flash read interface

Verified: `0x1C49C` adds `0x380000` to the resource offset and calls `0x124DC` in chunks of at most 1024 bytes.
The current file occupies external flash `[0x380000,0x3B8294)`.

| PSoC address | Read transaction role | Evidence |
|---|---|---|
| `0x60800031..0x60800033` | Three-byte flash address, low byte first | Verified `0x12334` |
| `0x6080002F..0x60800030` | Requested byte count, low byte first | Verified `0x124DC`, `0x12658` |
| `0x6080002E` | Write `0x12` to request a read. Bit 0 marks busy. | Verified `0x124DC`, `0x12370` |
| `0x60800C00..0x60800FFF` | Read result buffer | Verified `0x124DC` |

Unknown: the serial flash opcode that the FPGA emits internally.
The value `0x12` is the FPGA control value, not proof of a chip-level flash opcode.

### Checksums and version report

Verified: `0x218EC` implements CRC-8 with polynomial `0x07`, initial value zero, no reflection, and no final XOR.
Its 16-bit expression `~(value ^ 0x7C7F)` followed by a shift reduces to that byte algorithm.

| Check | Covered bytes | Result | Evidence |
|---|---|---|---|
| Header/index CRC | `[0,16)` then `[20,0x404)` | `0x29` | Verified, `0x1C4F4`, offline calculation |
| Full resource CRC | `[0,230036)` | `0x1B` | Verified, `0x1C5D4`, offline calculation |
| Standard CRC test | ASCII `123456789` | `0xF4` | Verified, decoder test |

Verified: `0x17404` forms resource report bytes `[0, version_low, full_crc]`.
For this file, the computed bytes are `00 06 1B`.
`0x1AB68` instead forms `[version_high, version_low, 0]` before the full CRC path.
`0x18198` reports `[0, version_low, update_crc]` after a resource update.

### Asset inventory

Verified: the decoder exported every frame.
`/tmp/apogee-fw/work-front-panel/assets.tsv` records each dimension, payload offset, frame count, and byte extent.
`docs/firmware/names/front-panel.tsv` assigns descriptive names to all 126 payloads.
Names describe the visible bitmap, not recovered vendor symbols.

| IDs | Dimensions | Content | Status and evidence |
|---|---|---|---|
| `00`, `5A` | 17 × 14 | Blue connection icon and amber status icon | Verified pixels at `0x404`, `0x20EB4`. Exact icon terminology is Unknown. |
| `01..1B` | 30–70 × 15 | Group, high-pass symbol, Input, Insert, 48v, phase symbol, Soft Limit, Inst, Mic, Off, On, reference levels | Verified pixels `0x5E0..0xA233` |
| `1C`, `1D` | 16 × 14, 13 × 14 | `IN`, `G` | Verified pixels `0xA234`, `0xA3F4` |
| `1E..27` | 10 × 14 | Digits 0–9 | Verified pixels `0xA560..0xB04F` |
| `28`, `29` | 5 × 12, 7 × 12 | Minus and plus | Verified pixels `0xB050`, `0xB0C8` |
| `2A..35`, `3F`, `62..63` | 8–19 × 9–12 | Compact group, phase, soft-limit, high-pass, input-type, and insert indicators | Verified exported bitmaps and `0x1DF30` |
| `36..3E` | 23 × 10 | `INT`, `WC`, `CX`, `OP1`, `OP2`, with green/red pairs | Verified pixels `0xBD4C..0xCD77` |
| `40..49` | 30 × 15 | Group numbers 1–5, bright/dim pairs | Verified pixels `0xCE74..0xF19B` |
| `4A..4D` | 20 × 32 | Microphone, phantom microphone, guitar, line connector | Verified pixels `0xF19C..0x1059B` and `0x1DF30` |
| `4E` | 18 × 9 | Lower interior of the numeric control graphic | Inferred composition from `0x1EBFC`, table `0x1FFF8B4C` |
| `4F` | 38 × 14 × 31 frames | Upper arc, progressively purple | Verified pixels `0x106E0..0x187B7` |
| `50`, `51` | 11 × 19 × 31 frames each | Left and right arc segments | Verified pixels `0x187B8..0x1ECF3`, `0x1EBFC` |
| `52` | 8 × 10 × 10 frames | Digits 0–9 for gain/attenuation | Verified pixels `0x1ECF4`, `0x1EBFC` |
| `53` | 11 × 14 × 10 frames | Digits 0–9 for sample rate | Verified pixels `0x1F334`, `0x1D320` |
| `54..59` | 10–23 × 20 | Speaker, muted speaker, headphones, numbers 1–3 | Verified pixels `0x1FF3C..0x20EB3`, `0x1D10C` |
| `5B`, `5C`, `5D` | 73 × 61, 90 × 18, 112 × 13 | Apogee logo, APOGEE, website text | Verified pixels `0x21090`, `0x2335A`, `0x24002` |
| `5E`, `5F` | 72 × 15, 88 × 12 | `Updating.`, `Please wait.` | Verified pixels `0x24B62`, `0x253D2` |
| `60`, `61` | 133 × 58, 29 × 106 | Thunderbolt reconnect instruction and cable graphic | Verified pixels `0x25C12`, `0x29856`, `0x1DD44` |
| `64..68` | 32–72 × 32 | Headphone/speaker/mute popup graphics | Verified pixels `0x2B352..0x2EF51` |
| `69..77` | 23–107 × 10–12 | Dim, meter clear, mono, mute, speaker set, stereo, headphone, and talkback text | Verified pixels `0x2EF52..0x3362B` |
| `78` | 138 × 28 | `ensemble` wordmark | Verified pixels `0x3362C`, boot draw `0x18CA4` |
| `79..7B` | 33–69 × 32 | Guitar output labels G1, G2, G1 G2 | Verified pixels `0x3545C..0x3761B` |
| `7C`, `7D` | 34 × 12, 99 × 12 | `Thru`, `From Software` | Verified pixels `0x3761C`, `0x3794C` |

Unknown: original font family, artwork source, and resource compiler.
The RGB565 conversion does not emulate the controller gray-scale table or the panel optical response.
No character map or vector font parser appears in the cited draw path.

### PSoC-resident fallback graphics

Verified: `0x18874` indexes 14 descriptors at RAM `0x1FFF853C`, initialized from flash `0x2580C`.
Each descriptor has five 32-bit fields: constant 1, width, height, byte count, and a bitmap pointer.
`0x188D0` expands consecutive bits, least-significant bit first, into foreground RGB565 or black.

| IDs | Content | Status and evidence |
|---|---|---|
| 0 | Small `v` glyph | Verified descriptor `0x1FFF83F0`, offline bitmap |
| 1–10 | Digits 0–9, height 9 | Verified descriptors `0x1FFF840C..0x1FFF8508` |
| 11 | Dot, 2 × 9 | Verified descriptor `0x1FFF8524` |
| 12 | `Updating.`, 72 × 15 | Verified descriptor `0x1FFF860C` |
| 13 | `Please wait.`, 88 × 12 | Verified descriptor `0x1FFF8574` |

Verified: `0x1DC54` draws fallback IDs 12 and 13 directly, without a resource read.
This permits update text while the external resource region changes.
The last sentence is Inferred from those independent data paths.

Verified: startup table `0x253C4` copies flash `0x253D8` to RAM `0x1FFF8108`, for `0xDC8` bytes.
This establishes the initializer addresses above, through `0x21970`.

## Display and graphics reference

### Controller interface

Inferred: both display controllers are SEPS525 or register-compatible parts.
The complete initialization and address commands match SEPS525 pages 17–27.
The binary contains no physical chip identifier in this path.

| Function | Operation | Status and evidence |
|---|---|---|
| `0x10910` | Select command path: display 0 → 0, display 1 → 1 | Verified calls to `0x222F8` |
| `0x10934` | Select data path: display 0 → 2, display 1 → 3 | Verified calls to `0x222F8` |
| `0x222F8` | Write `CYREG_B1_UDB05_CTL` | Verified code |
| `0x10988` | Wait for transmit status, send command, select data, send parameter | Verified code |
| `0x109DC` | Send a byte buffer through `0x22B94` | Verified code |
| `0x22B94` | Wait for `CYREG_B0_UDB10_ST & 4`, then write `CYREG_B1_UDB09_F0` | Verified code |
| `0x10C40`, `0x10C74` | Set inclusive X/Y window with registers `0x17..0x1A` | Verified code and SEPS525 page 26 |
| `0x10CA8` | Set current X/Y pointer with registers `0x20`, `0x21` | Verified code and SEPS525 page 27 |
| `0x10CDC` | Select pixel port `0x22` | Verified code and SEPS525 page 27 |
| `0x10D54`, `0x10DCC` | Fill entire display or inclusive rectangle with a two-byte color | Verified loops |
| `0x10F78` | Initialize one controller, clear it, enable it | Verified calls for displays 0 and 1 from `0x100EC` |

Inferred: the UDB transmit component supplies a shared serial display bus, with separate display/command selection.
Evidence: `0x10988`, `0x109DC`, FIFO access at `0x22B94`, and SEPS525 serial protocol on pages 9–10.
Unknown: board pin numbers, serial clock frequency, and the external select circuit.

| Register | Initialization | Meaning | Evidence |
|---|---|---|---|
| `04` | 1 then 0 | Reduced-current control | Verified `0x10F78`, SEPS525 page 20 |
| `02`, `03` | `01`, `60` | Oscillator control and clock divider | Verified `0x10F78`, pages 18–19 |
| `06` | `80`, then final `81` | Display off, then on | Verified `0x10AB4`, page 20 |
| `13`, `14`, `15`, `16` | `00`, `31`, `00`, `66` | Scan, external interface, polarity, memory access | Verified `0x10F78`, pages 23–25 |
| `28`, `29` | `7F`, `00` | 128-row duty and start line | Verified `0x10F78`, page 29 |
| `08..0A` | `02 03 00` | RGB precharge time | Verified `0x10ADC`, page 21 |
| `0B..0D` | `1A 19 0A` | RGB precharge current | Verified `0x10B28`, page 22 |
| `10..12` | `2F 31 1E` | RGB drive current | Verified `0x10B74`, page 22 |
| `50`, `51` | 96 index/data pairs | Gray-scale table from flash `0x251B4` | Verified `0x10F00` |
| `2E`, `2F`, `33..36` | `00`, `00`, `00 9F 00 7F` | Display area and source window | Verified `0x10E8C`, page 17 |
| `80` | `00` | External reference resistor mode | Verified `0x10D34`, page 19 |

### Draw queues and widgets

| Object or function | Behavior | Status and evidence |
|---|---|---|
| RAM `0x1FFF9270`, `0x1FFF93FC` | One queue per display, 48 eight-byte slots, one slot reserved | Verified `0x1C924`, `0x1CB80`, `0x1CB18` |
| `0x19038` | Execute at most three commands per display per call | Verified loop bounds |
| `0x1900C` | Drain both queues synchronously | Verified loop |
| Queue command 1 | Draw whole resource | Verified `0x1C9A4` → `0x1A9C0` |
| Queue command 2 | Fill rectangle | Verified `0x1C950` → `0x1C440` |
| Queue commands 3, 4, 5 | Set meter layout, select meter range, clip or restore meter area | Verified `0x19038`, `0x1B720`, `0x1B5E0`, `0x1C1AC` |
| Queue command 6 | Draw resource frame | Verified `0x1C9E8` → `0x1AA94` |
| `0x1C2A0`, `0x1C334`, `0x1C428` | Track window and pixel cursor, restore it after another draw path | Verified code |
| `0x1CF58` | Choose resource by value and state mask. `0x7F` means no image. | Verified four-byte choice entries |
| `0x1CDD8`, `0x1CE08` | Mark widget dirty after a value or state-mask change | Verified byte at widget `+7` |
| `0x1CC30` | Run page update callback and redraw dirty widgets | Verified code |

Verified: widget records are 16 bytes at `0x1FFF8A54` and other page tables.
They contain command, channel, X/Y, value, state mask, dirty flag, display, choice count, and choice-table pointer.
Evidence: `0x1CCD4`, `0x1CD5C`, `0x1CE34`, `0x1CEA0`.

| Widget offset | Field | Evidence |
|---|---|---|
| `+1`, `+2` | Command and channel | Verified `0x1CCD4` |
| `+3`, `+4` | X and Y | Verified `0x1CE34` |
| `+5`, `+6`, `+7` | Value, state mask, dirty flag | Verified `0x1CDD8`, `0x1CE08` |
| `+8`, `+9` | Display and choice count | Verified `0x1CE34`, `0x1CEA0` |
| `+12` | Pointer to four-byte choices: resource ID, value, allowed mask | Verified `0x1CF58` |
| `+0`, `+10..11` | Unresolved fields or alignment bytes | Unknown, not used by the cited consumers |

## UI and physical controls reference

### Pages and timers

Verified: `0x19390` coordinates encoder reads, meter updates, page updates, and queued draws.
`0x20364` complements Timer0 capture through `0x232BC`.
`0x20378` computes elapsed ticks, with an extra subtraction of one across wrap.
Unknown: the Timer0 route and tick duration. All durations below remain ticks.

| State | Entry and behavior | Status and evidence |
|---|---|---|
| Startup artwork | Logo at `(44,22)`, APOGEE at `(36,87)`, ensemble at `(15,51)`, version 1.5.3 at Y=84 | Verified `0x18CA4`, `0x18BA8` |
| Startup gate | Wait until elapsed ticks exceed 2000, then draw normal pages | Verified `0x19390`, flag `0x1FFF95BC` |
| Input home | Page pointer `0x1FFF8950`, input/gain graphic and ten meters | Verified `0x1DA30`, `0x1DF30`, `0x1B720` |
| Input menu | Page pointer `0x1FFF8B34`, filtered controls for selected input | Verified `0x1DA7C`, `0x1E4D0` |
| Output home | Page pointer `0x1FFF8874`, selected output, attenuation, sample rate, sixteen meters | Verified `0x1DACC`, `0x1D10C`, `0x1D320` |
| Output popup | Page pointer `0x1FFF8BB0`, previous page at `0x1FFF9FF0` | Verified `0x1DB1C`, `0x1D9C0` |
| Firmware update | Clear displays, use resident text, animate three squares | Verified `0x1DC54`, `0x1DE0C` |
| Reconnect instruction | Draw resources `60`, `61` | Verified `0x1DD44` |
| Functional test | Command `0x50` sets flag `0x1FFF95D4` and invokes test code | Verified `0x19738`, `0x1F26C` |
| Identify | Command `0x27` schedules callback `0x10544` every 30 timer ticks | Verified dispatcher `0x16228`, timer `0x2019C` |

| Timer action | Tick condition | Evidence |
|---|---|---|
| Meter sample | `elapsed > 29` | Verified `0x19208` |
| Queue service | `elapsed > 19` | Verified `0x19390` |
| Input long press | `elapsed > 749` | Verified `0x1FA94` |
| Input menu exit | `elapsed >= 18000` | Verified `0x19390` |
| Selected input LED blink | `elapsed > 450` | Verified `0x19390` |
| Pad transient LED | `elapsed > 1799` | Verified `0x19390` |
| Normal output popup | `elapsed >= 1800` | Verified `0x19390` |
| Meter-clear popup | `elapsed >= 600` | Verified `0x19390`, popup value `0x12` |
| Talkback popup | No timed exit while active | Verified `0x19390`, popup value `0x13` |
| External clock display refresh | `elapsed > 499` | Verified `0x19390` |
| Clock-change meter suppression | Through 1000 elapsed ticks | Verified `0x1A92C`, `0x19208` |

Verified: command `0x24`, LockHomeScreen, has no direct branch in `0x19738` or the panel loop.
Unknown: any effective home-lock behavior outside these paths. Do not infer enforcement from the host command name.

### Encoders and input selectors

| Control | Count reader | Effect | Status and evidence |
|---|---|---|---|
| Input encoder | `0x22EA0` | Adjust input gain, or select a menu item | Verified `0x19390`, `0x18F00` |
| Speaker encoder | `0x22DEC` | Adjust command `0x11`, output 2, unless main mode is Line | Verified `0x19390`, `0x18E5C` |
| Headphone 1 encoder | `0x22F54` | Adjust command `0x11`, output 0 | Verified `0x19390` |
| Headphone 2 encoder | `0x23008` | Adjust command `0x11`, output 1 | Verified `0x19390` |
| Input encoder push | Button index 0 | Cycle input on home, or change the selected menu value | Verified `0x1A778`, `0x1A5F8` |
| Output encoder pushes | Button indices 1, 2, 3 | Toggle speaker, headphone 1, headphone 2 mute | Verified `0x1A778` |

Verified: count readers subtract `0x8000` from hardware counts and return signed 16-bit positions.
Initialization seeds each counter to `0x8000`.
Evidence: `0x22DC0..0x23008`, counter readers `0x234C4`, `0x23670`, `0x2381C`, `0x239C8`.
Unknown: encoder detents, pulses per revolution, and board pin assignments.

Verified: the ten selector indices map to audio channels `0,1,2,3,10,4,5,6,7,11`.
Evidence: `0x21640`, RAM `0x1FFF8EB0`, flash `0x26180`.
Thus selectors 4 and 9 select Guitar 1 and Guitar 2, not the front microphone.
The cycle order is `0,1,2,3,5,6,7,8,4,9,0` at `0x1A88C`.

Verified: an input press selects it. A press on the current input toggles its menu.
A held selector toggles the menu after more than 749 ticks.
Evidence: `0x19AEC`, `0x19BF4`, `0x1FA94`.

Verified: input gain limits are 75 for Mic, 65 for rear Instrument, and 45 for Guitar.
Output attenuation spans 0–64.
Evidence: `0x18F00`, `0x18E5C`.

Verified: menu command slots are `01,04,07,0A,06,05,08`: input type, soft limit, group, insert, phase, phantom, high-pass.
Evidence: fourteen widget records at RAM `0x1FFF8A54`, value half at `+7*16`.
`0x1E4D0` filters them by input type, channel, and partner type.
Guitar inputs expose Group only. Insert is available only on channels 0 and 1.

### Pad assignments

Verified: command `0x25`, parameter 0–3, chooses the local pad action below.
These values differ from the host remote-button enum.
Evidence: `0x1A1B0`, `0x1A140`, `0x1A4E4`, `0x19D78`.

| Value | Local pad action | Constraints |
|---:|---|---|
| 0 | None | LED off |
| 1, 2, 3 | Toggle speaker, headphone 1, headphone 2 mute | Speaker requires a non-Line main mode |
| 4 | Toggle mute on all three outputs | `0x19CB8` uses the aggregate state |
| 5 | Alternate speaker and headphone mute | In Line mode, toggle all mute |
| 6, 7, 8 | Toggle speaker, headphone 1, headphone 2 dim | Speaker requires a non-Line main mode |
| 9 | Toggle dim on all three outputs | Aggregate state |
| 10, 11, 12 | Toggle speaker, headphone 1, headphone 2 mono | Speaker excludes Line and surround modes |
| 13 | Toggle mono on all three outputs | Aggregate state |
| 14, 15, 16 | Select speaker set A, B, C | Main mode 2 or 3. C requires mode 3. |
| 17 | Alternate speaker sets A/B | Main mode 2 or 3. Does not cycle through C. |
| 18 | Clear both meter banks | Also emits command `0x28` |
| 19 | Momentary talkback | Press sets `0x19=1`, release sets `0x19=0` |
| 20, 21, 22 | Toggle Guitar 1, Guitar 2, or both output modes | Command `0x16`, Thru versus From Software |

### Input and LED hardware

Inferred: two Semtech SX1509-compatible GPIO expanders service switches and LEDs.
Evidence: I2C addresses `0x70/0x71`, reset sequence `0x7D←0x12,0x34`, and exact GPIO/LED register map.
Sources: `0x128AC`, `0x128E8`, `0x12B84`, `0x12C20`, SX1509 pages 14 and 30–34.
Unknown: the capacitive sensor or switch circuit before the expander inputs.
An SX1509 register match does not identify a capacitive touch controller.

| Input group | I2C device | Active-low masks, in logical order | Evidence |
|---|---|---|---|
| Ten selectors | `0x71` | `0001 0002 0004 0008 0100 0200 0400 0800 4000 8000` | Verified `0x1FA94`, RAM `0x1FFF8BC8`, flash `0x25E98` |
| Four pads | `0x70` | `0800 0200 0400 0100` | Verified RAM `0x1FFF8BDC`, flash `0x25EAC` |
| Encoder pushes: input, speaker, HP1, HP2 | `0x70` | `0004 0008 0001 0002` | Verified RAM `0x1FFF8BE4`, flash `0x25EB4` |

Verified: `0x12B84` reads register `0x11` as the low byte and `0x10` as the high byte.
`0x12BD0` reads interrupt registers `0x18/0x19`, then writes `0xFF` to both.
The event loop emits only new press/release transitions and reenables the interrupt afterward.
Evidence: `0x1FA94`, interrupt callbacks `0x1F9B8`, `0x1F9DC`.

Verified LED map from RAM `0x1FFF811C`, initialized at flash `0x253EC`:

| Logical LEDs | Expander and pins | Evidence |
|---|---|---|
| Input selectors 0–9 | `71:4, 71:5, 71:7, 71:12, 70:4, 70:5, 70:12, 70:15, 71:6, 71:13` | `0x1279C`, `0x12778`, `0x12C20` |
| Pads 0–3 | `70:6, 70:7, 70:13, 70:14` | Same map entries 10–13 |

Verified: `0x12C20` uses a five-register table at RAM `0x1FFF813C` for each LED.
It clears timer/ramp registers and writes intensity through the second table entry.
Intensity zero sets the GPIO data bit. Nonzero intensity clears it.
Evidence: `0x12C20`, SX1509 static LED mode, pages 19 and 34.

Verified: the UI commonly writes `0x10` for dim and `0x70` for active.
`0x19B60` also uses `0x50` for guitar selectors.
Pad LEDs reflect assigned action state through `0x19D78`.
Unknown: actual optical brightness and current without the LED circuit values.

Verified: Identify uses a separate PSoC output, not the OLED draw queue.
Callback `0x10544` calls `0x10514`, which changes port P3[3] data and drive mode through `0x2200C` and `0x22048`.
Unknown: the physical indicator that P3[3] drives. The register path alone does not establish a power LED.

## Meter reference

Verified: when the clock gate permits, `0x19208` reads 26 little-endian 16-bit values from PSoC address `0x60800040`.
The first ten feed the input display. The next sixteen feed the output display.
`0x19738` sets that gate from Internal clock selection or report `0x64`. A closed gate substitutes zeros.
It writes 3 to FPGA byte register `0x80` through `0x12130` before the sample loop.
Unknown: whether that write latches, acknowledges, or clears an FPGA accumulator.

Verified: if bit 15 is set, the PSoC replaces the word with `(word & 0x3FFF) | 0x4000`.
The meter renderer uses bit 14 as the over indicator.
Evidence: `0x19208`, `0x1BC14`.

| Meter order | Signal | Status and evidence |
|---|---|---|
| 0–7 | Analog inputs 1–8 | Verified startup route table, `0x14020`, `0x140E8` |
| 8–9 | Guitar inputs 1–2 | Verified same route path |
| 10–19 | Line outputs 1–10 | Inferred from output route destinations and `0x13D10` |
| 20–21 | Guitar outputs 1–2 | Inferred from output pair 5 and `0x13D10` |
| 22–25 | Headphone 1 L/R, headphone 2 L/R | Inferred from output pairs 15/16 and `0x13D10` |

Verified: `0x1C13C` counts crossed thresholds and returns seven pixels per threshold, at most 63 pixels.
The thresholds at RAM `0x1FFF87E4`, flash `0x25AB4`, are:

```text
65, 326, 1033, 2596, 4115, 5813, 8211, 11598, 14602
```

Inferred: relative to full-scale 16384, these approximate −48, −34, −24, −16, −12, −9, −6, −3, −1 dBFS.
Evidence: arithmetic conversion and the prior meter-scale measurements in `NOTES-vendor-driver.md` section 4.4.

Verified: `0x1B720` places normal meter bars at Y=60, with height parameter 65.
Ten input bars are eight pixels wide. Sixteen output bars are five pixels wide.
Over indicators sit at Y=51 with height seven.

Verified: `0x1AC30` selects row colors from three-byte entries at RAM `0x1FFF86A8`, flash `0x25978`.
Each entry contains a row limit and an RGB565 color in high-byte-first order.
The background is `0x18C3`. The active over indicator is `0xF0C1`.
Evidence: `0x1ADC0`, `0x1AE30`.

Verified: peak and over hold modes are 0 off, 1 finite, and 2 indefinite.
The finite threshold is `2000000/30000 = 66` update counts, with strict `>` comparisons.
The normal fall rate is `elapsed_ticks*5/30` pixels after two lower-level updates.
Evidence: `0x1B3CC`, `0x1BC14`, `0x1B9C8`, `0x1BA58`.
Do not convert these counts to wall-clock seconds until the timer route is known.

## Offline reproduction and tests

Run the decoder without any device connection:

```sh
uv run --with pillow python scripts/firmware/front-panel-resources.py \
  '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsembleResourceData.bin' \
  /tmp/apogee-fw/work-front-panel
PYTHONDONTWRITEBYTECODE=1 python3 scripts/firmware/front-panel-test.py
```

Verified output from this run:

```text
sha256=3febcf6f14123ca9767fe651a87fc6fd5ba875dbe52fadf0b3160ce73bdb290b
assets=126 frames=234 crc8=0x1b
```

| Artifact under `/tmp/apogee-fw/work-front-panel` | Status and purpose |
|---|---|
| `contact.png` | Verified first frame of every asset, with ID and dimensions |
| `asset-XX-NN.png` | Verified RGB565 conversion of every resource frame |
| `frames-4f.png`, `frames-50.png`, `frames-51.png` | Verified 31-frame arc sequences |
| `frames-52.png`, `frames-53.png` | Verified two decimal digit fonts |
| `assets.tsv` | Verified complete index and payload extents |
| `builtin-00.png` through `builtin-0d.png`, `builtins.png` | Verified one-bit images from PSoC initialized data. Separate offline extraction. |
| `boot-panels.png` | Inferred screen composition from exact `0x18CA4` and `0x18BA8` coordinates. No device photograph. |

Verified: `contact.png` SHA-256 is `abf9eeb2a7c524ec5e3e61c64bdea5865ea22cce5287aefc096b464f3cf96bbe`.
Verified: `boot-panels.png` SHA-256 is `7e6a5f91e34ae3f57785615f6bb0daeb6363cfd9c2840915bf4083c2c533b43d`.

Verified: decoder tests cover CRC, byte order, frame selection, truncated files, bad headers, unsupported kinds, invalid counts, and bad extents.
Four decoder tests, seven digital signal processor (DSP) unit tests, and 39 control-model tests passed.
The control suite used a separate `/tmp/apogee-fw/work-front-panel/swift-build` directory and fake transport.
Ruff format/check and Python byte compilation passed for both new scripts.

Verified: the decoder deliberately rejects noncontiguous payloads and unsupported record kinds.
The firmware loader does not impose those checks.
Unknown: whether another resource version permits gaps, extra kinds, or a nonzero unused header field.
The decoder is an extractor, not a safe firmware packer.

## Safety notes

| Status | Hazard | Evidence and required limit |
|---|---|---|
| Verified | Resource count can overwrite RAM before CRC validation. | `0x1C4F4` writes eight bytes per unbounded header count. Cache `0x1FFF9B78..0x1FFF9F67` fits exactly 126 records. Keep count at 126 or less. |
| Verified | Dimensions and payload offsets lack file-bound checks. | `0x1C720`, `0x1C7C0`. Validate every extent offline. |
| Verified | Frame index lacks a check against frame count. | `0x1C7C0` adds an arbitrary frame stride. Validate every call and choice table. |
| Verified | The full CRC path trusts the header length. | `0x1C5D4` passes it directly to `0x12570`. Bound the resource length. |
| Verified | External flash updates erase and program immediately. | `0x18098` calls `0x123E0` at 64 KiB boundaries and `0x12444` per page. Do not invoke these paths for inspection. |
| Verified | Resource update bounds are broader than the file. | `0x1836C` accepts addresses `0x380000..0x7FFFFF` for target 1. This does not prove installed flash capacity. |
| Verified | Read timeouts do not stop the normal read helper. | `0x124DC` records an error but still copies the FPGA buffer. Do not treat a successful resource draw as flash integrity proof. |
| Verified | SPI and I2C waits can block forever. | `0x10988`, `0x22B94`, `0x11050`, `0x110F0` contain unbounded waits or retries. |
| Verified | Draw queues silently drop commands when full. | `0x1CB80` returns false. Callers such as `0x1C9A4` do not retry. Preserve bounded queue load. |
| Verified | Coordinates narrow to eight bits without clipping. | `0x1A9C0`, `0x1AA94`, `0x10DCC`. Keep rectangles within 160 × 128. |
| Inferred | OLED current changes can exceed the panel specification. | `0x10B28`, `0x10B74`, SEPS525 page 22. Preserve vendor current and precharge values. |
| Verified | UI actions can change audible output and phantom power. | `0x1A778` toggles mute, `0x1A5F8` dispatches command `0x05`. Keep behavioral tests offline. |

## Explicit gaps and proposed tests

| Status | Gap | Offline next test |
|---|---|---|
| Unknown | Timer duration and GPIO-to-package pin map | Trace Timer0 source and digital routes through configuration bytes. No device access. |
| Unknown | Physical OLED part and exact SPI route | Match package markings or a board schematic to the SEPS525-compatible register map. |
| Unknown | Flash manufacturer, capacity, and resource erase protection | Correlate FPGA flash logic with the updater map. `0x380000` alone does not identify the chip. |
| Unknown | Home-lock enforcement | Trace all reads of the stored command `0x24` value beyond panel code. |
| Unknown | Exact optical brightness and meter color calibration | Compare an owner-provided display photograph with the exported assets. No command is required. |
| Unknown | Original symbol names, fonts, and resource authoring tool | Compare artwork metadata from an original vendor project, if available. |

No on-device command is proposed.
The offline decoder and tests above provide exact, reproducible commands with no flash or hardware risk.
