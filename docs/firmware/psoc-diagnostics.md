# PSoC functional diagnostics and panel callbacks

**Verified:** The diagnostic cluster controls displays, LEDs, reports, and the front-microphone gain mode, not a demonstrated audio test generator.
Evidence: `0x1F0C0..0x1F554`, mode helpers `0x12FD0/0x13000`, and the call paths below.

## Scope and evidence

PSoC means the Cypress programmable system-on-chip in the Ensemble Thunderbolt interface.
FPGA means field-programmable gate array.
ADC means analog-to-digital converter. DAC means digital-to-analog converter.
AGC means automatic gain control. PGA means programmable gain amplifier.
I2C means Inter-Integrated Circuit, the serial control bus. LED means light-emitting diode.
RAM means volatile memory. EEPROM means electrically erasable persistent memory.
RGB565 means a pixel with five red, six green, and five blue bits.
CPU means central processor. Thumb is its compact instruction set.
TSV means tab-separated values. PDF means Portable Document Format.
A callback is a function whose address resides in a table for an indirect call.

- **Verified:** Direct instruction, table-byte, or identified document evidence.
- **Inferred:** A conclusion from the cited evidence, without physical verification.
- **Unknown:** Evidence does not establish the stated identity or effect.

**Verified:** This report used static files and vendor datasheets only. No device command, updater, register access, or shared Ghidra project change occurred.

| Input                                                                                            | Identity or purpose                                                            |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| `/tmp/apogee-fw/flash.bin`                                                                       | SHA-256 `a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8`     |
| `/tmp/apogee-fw/decompiled.c`, `functions.tsv`                                                   | Baseline function boundaries and decompile                                     |
| `docs/firmware/function-coverage.tsv`                                                            | Coverage before this second pass                                               |
| `front-panel.md`, `psoc-audio.md`, `psoc-protocol.md`, `psoc-startup.md`, `psoc-update.md`       | Prior maps under `docs/firmware`, left unchanged                               |
| `NOTES-vendor-driver.md`, `probe-results.md`                                                     | Host command names and prior observations, not new device tests                |
| [Texas Instruments TLV320ADC3101 datasheet](https://www.ti.com/lit/ds/symlink/tlv320adc3101.pdf) | SLAS553B, August 2015, printed pages 25–26, 55, 57–61, 65–68                   |
| Same PDF                                                                                         | SHA-256 `0ffb85b5833b851e363d099f9735ece8137b965ffde0cbf52b66a3b44e3ccbd1`     |
| [Texas Instruments TLV320ADC3100 datasheet](https://www.ti.com/lit/ds/symlink/tlv320adc3100.pdf) | SBAS906, March 2018, pages 60, 67–68, 78, 81, for an alternate-part comparison |

**Verified:** CPU flash address minus `0x10000` gives the offset in `flash.bin`.
Startup copies flash `0x253D8` to RAM `0x1FFF8108` for `0xDC8` bytes (`0x21970`, descriptor `0x253C4`).
This relocation supplies each RAM/flash table pair below.

**Verified:** The coverage input contains 40 function entries in `[0x1E000,0x1F800)`, of which 36 lack names.
The new names file covers all 36 and two callbacks absent from the baseline: `0x1E184` and `0x1F8D8`.
The report follows `0x1F660` through its return at `0x1F8C2`, beyond the requested approximate endpoint.
It also names the related bit-index helper `0x1FD48` and both ADC mode helpers.

**Unknown:** Original vendor symbol names. New names describe visible operations, not recovered source identifiers.

## Explanation

### Three independent states

**Verified:** The firmware does not represent diagnostics with one state variable.

| Address                  | Width | Meaning and exact evidence                                                                                            |
| ------------------------ | ----: | --------------------------------------------------------------------------------------------------------------------- |
| `0x1FFF95D4`             |     4 | Special-panel gate. `0x199FC` clears it for command `0x50=0`. `0x19A10` sets it for any nonzero value.                |
| `0x1FFFA020`             |     1 | Functional mode. `0x1F36E` stores the changed command byte. Service recognizes only 1 and 2 (`0x1F0E2/0x1F0E6`).      |
| `0x1FFF8184`             |     4 | Requested ADC gain-control mode. `0x12FF4` stores 1. `0x13024` stores 0. `0x12F44` selects the gain register from it. |
| `0x1FFF8F08`             |     4 | Hardware-revision path, not a diagnostic state. `0x104E4` compares revision with 2 and `0x104EE` calls `0x12D28`.     |
| `0x1FFFA022`             |     2 | Diagnostic LED toggle mask. Entry to mode 1 clears it at `0x1F2C6`.                                                   |
| `0x1FFFA024..0x1FFFA02B` |     8 | Four encoder snapshots, signed 16-bit values, initialized at `0x1F2D2/DE/EA/F6`.                                      |

**Inferred:** `0x1FFF8184=1` requests AGC, while zero requests manual PGA control on the newer hardware path.
Evidence: exact register matches in the component section below.

**Verified:** Startup clears the functional mode through `0x1F0C0`, but that helper does not access the ADC or reset the report fields.
The startup RAM-clear loop separately zeroes the diagnostic mask and snapshots (`0x21970`).

### Command entry and transition matrix

**Verified:** Internal command bytes are ID at `+8`, first parameter at `+9`, second parameter at `+10`, and first data byte at `+11`.
The mode handler consumes `+11`, not the first parameter (`0x1F284`).
The parser supplies this byte from the value in a type-1 record (`0x154B2`).

**Verified:** Command `0x50` takes the main dispatcher's default path, then the panel hook.
Command `0x51` first tests data against `0xAB` (`0x16F1E`).
The dispatcher invokes the panel hook for nonzero sources (`0x16F90..0x16F96`).
Normal sources are 0 local, 1 host, and 2 EEPROM replay.

| Input through the panel hook           | Verified transition and effects                                                                                                                     | Instruction evidence                                              |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `0x50`, value 1, previous mode differs | Detach normal pages. Set special gate. Draw color bars. Clear all 14 LEDs and toggle mask. Snapshot encoders. Disable AGC. Store mode 1.            | `0x19A08..0x19A14`, `0x1F2A0..0x1F2F8`, `0x1F36E`                 |
| `0x50`, value 2, previous mode differs | Detach normal pages. Set special gate. Clear both screens. Enable input/output meter layouts. Set all 14 LEDs to `0x70`. Disable AGC. Store mode 2. | `0x1F2FE..0x1F35C`, `0x1F36E`                                     |
| `0x50`, value 0, previous mode differs | Clear special gate. Restore ordinary panel state and pages. Enable AGC. Store mode 0.                                                               | `0x199F8..0x19A02`, `0x1F362..0x1F36E`                            |
| `0x50`, same value as current mode     | Panel-hook actions still occur. The inner mode handler skips all entry actions and ADC writes.                                                      | Outer hook `0x199F0..0x19A14`, equality branch `0x1F28A..0x1F28C` |
| `0x50`, changed value 3–255            | Detach normal pages and set special gate. Store the unsupported mode. No LED, meter-layout, or ADC setup in the inner handler.                      | `0x19A08..0x19A10`, `0x1F292..0x1F29E`, `0x1F368..0x1F36E`        |
| `0x51`, any data, source 1 or 2        | Enable AGC through the panel hook. Do not change functional mode, special gate, toggle mask, or snapshots there.                                    | `0x19A1A..0x19A1C`, `0x1F374`                                     |
| `0x51`, data `0xAB`, any normal source | Additionally request the deferred factory reset, through `0x17004`.                                                                                 | `0x16F1E..0x16F22`, state store `0x1700C`                         |
| `0x50`, source 0                       | No functional mode change through the dispatcher. There is no state descriptor, and the dispatcher skips the panel hook.                            | `0x16F8A..0x16F96`, descriptors `0x25EBC..0x2609B`                |
| `0x51`, source 0                       | `0xAB` still requests factory reset. The dispatcher skips the ADC-mode panel hook.                                                                  | `0x16F1E..0x16F22`, `0x16F90..0x16F92`                            |

**Verified:** A non-`0xAB` host reset command is not inert. It still reaches the AGC-enable helper.
The magic-byte check protects the default reset, not the ADC side effect.

**Verified:** Mode 2 does not clear the toggle mask or snapshots, and entry to mode 1 does not publish its cleared mask.
Evidence: no `0x1F408` call in `0x1F26C`, and separate mode-1 stores at `0x1F2C6..0x1F2F6`.
Thus report `0x52` can retain a prior value until a selector or pad release updates it.

**Verified:** `0x1D990` assigns an empty page to both displays and cancels the update animation flag.
It does not clear both displays itself.
Repeated or unsupported nonzero modes therefore do not guarantee a fresh diagnostic screen (`0x19A08`, `0x1F28C`).

### Service and ordinary-control isolation

**Verified:** `0x19390` calls `0x1F0D8` when the special gate is nonzero.
Mode 1 polls encoders. Mode 2 calls the ordinary meter service. Other modes return without either operation.
Display queues still run after that branch (`0x19390`, queue service `0x19038`).

**Verified:** Ordinary selector, long-press, pad, and encoder-push handlers test the special gate before their normal actions.
Evidence: `0x19AEC`, `0x19BF4`, `0x1A140`, `0x1A1B0`, and `0x1A778`.
The common input service still calls diagnostic callbacks (`0x1FA94`).

**Verified:** This gate does not suspend host commands, audio service, EEPROM service, or the scheduler.
The main loop calls those services independently (`0x1F986..0x1F9B2`).
The host can still alter gain, mute, phantom power, routes, or clock through `0x16228`.
The input service also retains its ordinary power-event call at `0x1FAA8`.

**Verified:** Diagnostics uses separate encoder snapshots from ordinary control.
Mode service updates `0x1FFFA024..0x1FFFA02B`, not the ordinary snapshots at `0x1FFF9590..0x1FFF9597`.
Neither exit helper, `0x18AF8` or `0x18D24`, refreshes those ordinary snapshots.

**Inferred:** Encoder movement during diagnostics can change ordinary gain or attenuation after exit.
The next normal service subtracts the old ordinary snapshot, then calls gain control at `0x1944E` or attenuation control at `0x19494`.
The headphone paths follow the same pattern in `0x19390`.
The resulting level change depends on net movement, selected input type, and output mode.

**Inferred:** A held momentary-talkback pad can remain logically active if diagnostics starts before release.
`0x1A140` skips its normal talkback-clear action under the special gate, while `0x1D990` does not clear command `0x19`.

**Verified:** Firmware-update mode also sets the special gate, but leaves the functional mode unchanged (`0x19A22..0x19A36`).
Update restore clears the gate but not the functional mode or ADC-mode flag (`0x19A4C..0x19A70`).
A preexisting diagnostic mode can therefore affect service during that shared-gate interval.

**Verified:** Converter reinitialization on a rate change calls `0x12D28`, whose newer path restores AGC and sets `0x1FFF8184=1`.
It does not clear functional mode (`0x104EE`, `0x12D28`).
A repeated mode-1 or mode-2 command then skips the ADC-disable operation because the mode byte already matches (`0x1F28C`).

## Diagnostic reference

### Reports are events, not pass/fail results

**Verified:** Both reports have one scalar state slot, not one slot per encoder or switch.

| ID     | Descriptor bytes at flash            | State-pool address        | Content                                    |
| ------ | ------------------------------------ | ------------------------- | ------------------------------------------ |
| `0x52` | `0x25F94`: `52 02 00 00 00 00 00 01` | `0x1FFFA1E7`, two bytes   | Little-endian LED toggle mask              |
| `0x53` | `0x25F9C`: `53 03 00 00 00 00 00 01` | `0x1FFFA1E9`, three bytes | Encoder index, event code, event magnitude |

Evidence: descriptor allocation `0x203B4`, writes `0x1F408`, `0x1F38C`, and `0x1F224`.
The descriptor's final byte marks both values volatile.

| Event                             | Report payload                        | Verified evidence                                                              |
| --------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------ |
| Selector or pad press             | None                                  | `0x1F188` only stores its argument on the stack, then returns at `0x1F198`     |
| Selector or pad release in mode 1 | `0x52`: low mask byte, high mask byte | `0x1F19C` toggles bit n and its LED, then calls `0x1F408` at `0x1F202`         |
| Positive encoder delta            | `0x53`: `[index,0,abs(delta)&255]`    | Positive comparison `0x1F3C4`, code store `0x1F3CA`, byte truncation `0x1F3E2` |
| Negative encoder delta            | `0x53`: `[index,1,abs(delta)&255]`    | Code store `0x1F3D0`, negate `0x1F3D6`, byte truncation `0x1F3E2`              |
| Encoder push                      | None                                  | `0x1F210` only stores its argument on the stack, then returns at `0x1F220`     |
| Encoder release in mode 1         | `0x53`: `[index,2,1]`                 | Bounds check `0x1F236`, data stores `0x1F24A..0x1F252`                         |

**Verified:** Encoder indices are 0 input, 1 speaker, 2 headphone 1, and 3 headphone 2.
The reader calls are `0x1F0EC`, `0x1F10E`, `0x1F130`, and `0x1F152`, respectively.
The delta calculation wraps through a 16-bit store before its signed comparison (`0x1F3A6..0x1F3C4`).
The magnitude field then truncates to eight bits. No overflow flag exists in this report.

**Verified:** Switch indices 0–9 follow physical selector order. Pad indices are 10–13.
The pad-release call is at `0x1FB4A`. The selector-release call is at `0x1FCB2`.
This order differs from audio channel numbers, which `0x21640` maps to `0,1,2,3,10,4,5,6,7,11`.

**Verified:** Report `0x52` represents alternate LED state after releases, not the current electrical switch levels.
The code toggles the bit. It does not copy an input-register mask (`0x1F1B6..0x1F202`).
It contains no ADC measurement, tolerance, pass bit, or completion result.

**Verified:** Writers call `0x20918` with source 0. The report scheduler later serializes the current stored bytes.
It sends type 2 because the widths are 2 and 3 (`0x15A10`, `0x2153C`).
Host availability still gates transmission (`0x15668`).

**Inferred:** Multiple encoder events before a report send collapse into the last stored event.
All four encoder calls write the same `0x53` slot, and the scheduler has one pending bit for that scalar property.
This is not an event queue or reliable movement log (`0x1F0D8`, `0x20918`, `0x21854`).

### Screen diagnostics versus electrical operations

| Operation                   | Verified code or table evidence                                           | Scope                                                                                                                 |
| --------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Four color bars per display | `0x1F444`, table RAM `0x1FFF8B60`, flash `0x25E30`: `0000 F800 07E0 001F` | RGB565 black, red, green, blue. Four 40 × 128 stripes on each 160 × 128 screen.                                       |
| White border                | `0x1F4CA/EE`, `0x1F512/36`, color `0xFFFF`                                | Two-pixel border at x=0/158 and y=0/126. Display output, not an audio waveform.                                       |
| Meter layouts               | `0x1F32E/3A` enable layouts 1 and 2                                       | Mode 2 uses the ordinary ten-input and sixteen-output meter renderer.                                                 |
| Meter data                  | `0x1F178 → 0x19208`                                                       | Reads 26 words at FPGA `0x60800040`, subject to ordinary lock/time gates. Writes 3 to `0x60800080` through `0x12130`. |
| LED output                  | `0x1F2B2`, `0x1F34C`, `0x1F1E2/FE → 0x12C20`                              | Actual I2C output changes on expanders `0x70/0x71`. Zero or intensity `0x70`.                                         |
| Front microphone            | `0x1F2F8/0x1F35C → 0x13000`                                               | Actual I2C write to ADC page 0 register `0x56`, on the newer path.                                                    |
| Factory reset               | `0x16F22 → 0x17004`, then `0x16000 → 0x20F5C`                             | Actual EEPROM write and later replay of audio settings. Not a screen-only reset.                                      |

**Verified:** Mode 2 does not populate synthetic meter samples. Its service calls `0x19208`, not a test-vector source.
The ordinary clock gate can substitute zeros (`0x19208`, state `0x1FFF95D8`).
**Unknown:** Exact hardware meaning of FPGA meter-control value 3. It is not proof of a signal-generator enable.

**Verified:** No call in `0x1F26C` writes a route, oscillator coefficient, rear preamp register, phantom command, or output DAC level.
The direct callees are display, LED, encoder, and ADC-mode helpers.
**Unknown:** Board voltages, acoustic output, and any independent FPGA test engine.
The host debug labels `BERT_STATE` and `SINE_*` do not prove that these PSoC modes enable such an engine.

### Front-microphone component identification

**Inferred:** The front converter is TLV320ADC3101-compatible, based on several independent register matches.
The firmware does not read a unique part ID in `0x12D28`, `0x12F44`, `0x12FD0`, or `0x13000`.
**Unknown:** Exact package, silicon revision, and physical microphone part.

| Firmware evidence                                                     | Datasheet evidence                                                                                                 | Conclusion                                                                                                     |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Newer path writes page 0 `56=80`, mode entry writes `56=00`           | TLV320ADC3101 p59, table 72, register 86 bit 7 enables left AGC                                                    | **Inferred:** Diagnostic entry disables left AGC. Mode exit enables it.                                        |
| `0x12F44` writes page 0 `58` while flag=1                             | p60, table 74, register 88 is left AGC maximum gain, 0.5 dB per count                                              | **Inferred:** Ordinary front-mic gain controls an AGC ceiling, not its target level.                           |
| `0x12F44` writes page 1 `3B` while flag=0                             | p68, table 101, register 59 is left PGA gain/mute                                                                  | **Inferred:** In diagnostics, the same gain command selects fixed analog gain and clears PGA mute.             |
| Newer initialization writes page 1 `33=40`                            | p65, table 93, bits 6:5=`10` select MICBIAS1 at 2.5 V                                                              | **Inferred:** The newer microphone path supplies analog microphone bias. Actual board voltage remains Unknown. |
| Newer initialization writes page 1 `34=FC`                            | p66, table 94, bits 1:0=`00` select IN1L at the documented 0 dB setting                                            | **Inferred:** The newer path selects the single-ended IN1L input.                                              |
| Newer initialization writes page 0 `51=80`, `52=08`                   | p58, tables 67–68, left ADC on, digital microphone off, right mute on                                              | **Inferred:** One active analog microphone channel.                                                            |
| Older initialization writes page 0 `33=28`, `34=04`, `50=02`, `51=88` | p55, tables 55–56, DMCLK emits the modulator clock and DMDIN accepts input. p57–58 select left digital microphone. | **Inferred:** Hardware revision ≤2 uses a digital microphone path through the same register family.            |
| Older gain path writes page 0 `53`, capped at 40                      | p58, table 69, register 83 is digital volume, 0.5 dB per count                                                     | **Inferred:** The old path caps digital gain at 20 dB.                                                         |

**Verified:** `0x14A24` accepts front-microphone host gain 0–40 and doubles it before `0x12F44`.
On the newer path, the maximum code is 80. On the older path, the maximum code is 40.
The ADC-mode helpers perform no I2C operation on the older path, but still change their RAM flag (`0x12FDA`, `0x1300A`).

**Verified:** The newer initialization sets AGC registers `56..5C` to `80 80 3C 50 00 0C 03` (`0x12D28`).
**Inferred:** Under the compatible part interpretation, these select the parameters below.

| Register    | Value | Interpretation                                                        | Datasheet evidence |
| ----------- | ----- | --------------------------------------------------------------------- | ------------------ |
| Page 0 `56` | `80`  | AGC enabled, target −5.5 dB relative to full scale                    | p59, table 72      |
| Page 0 `57` | `80`  | 4 dB hysteresis, noise detection disabled, clip-step feature disabled | p60, table 73      |
| Page 0 `58` | `3C`  | Maximum PGA gain 30 dB before saved gain replay                       | p60, table 74      |
| Page 0 `59` | `50`  | Attack parameter 21 × 32 converter samples                            | p60, table 75      |
| Page 0 `5A` | `00`  | Decay parameter 512 converter samples                                 | p60, table 76      |
| Page 0 `5B` | `0C`  | Noise debounce 8192 converter samples                                 | p61, table 77      |
| Page 0 `5C` | `03`  | Signal debounce 16 converter samples                                  | p61, table 78      |

**Verified:** `0x13000` writes only page select and AGC control. It does not copy the saved gain into the manual PGA register.
`0x12FD0` likewise does not copy manual gain back into the AGC maximum register.
**Unknown:** Immediate applied gain after the mode switch. Do not equate the stored host value with that instantaneous gain.

**Verified:** Both helpers write the entire `0x56` register, not just bit 7 (`0x12FE6..0x12FEC`, `0x13016..0x1301C`).
**Inferred:** Both also select target code zero, which means −5.5 dB on the compatible part.
This corrects the prior audio report's tentative target interpretation of register `0x58`, without changes to that report.

**Verified:** The TLV320ADC3100 shares AGC and PGA addresses, but marks page-1 register 52 bits 1:0 reserved at value 3.
It also marks page-0 register 51 reserved (ADC3100 pp60, 78).
**Inferred:** That part alone does not explain the firmware's `34=FC` analog input or older digital-microphone configuration.
The broader ADC3101 match is stronger than the AGC-address match alone.

### Persistence and reset side effects

**Verified:** Commands `0x50/0x51` have no state-table descriptor. Reports `0x52/0x53` are volatile.
Mode bytes, ADC-mode flag, mask, and snapshots are not included in a normal settings save (`0x20F5C`, descriptors `0x25EBC..0x2609B`).

**Verified:** Factory reset follows this deferred path:

| Phase           | Instruction evidence                                 | Effect                                               |
| --------------- | ---------------------------------------------------- | ---------------------------------------------------- |
| Request         | `0x16F1E` compares `0xAB`, `0x16F22` calls `0x17004` | Store protocol state 2 at `0x1FFF8F0C` (`0x1700C`)   |
| Default state   | `0x15FFC` calls `0x205CC`                            | Replace RAM property values with defaults            |
| Durable save    | `0x16000` calls `0x20F5C`                            | Synchronously replace the EEPROM settings image      |
| Version refresh | `0x16004` calls `0x17404`                            | Refresh hardware/resource version reports            |
| Replay          | Protocol state 1 at `0x15F9E..0x15FFA`               | Validate and replay EEPROM commands through source 2 |

**Verified:** The current settings image contains 42 descriptors and ends at EEPROM offset `0x50B`, exclusive.
The writer reaches `EEPROM_Write` at `0x23064` through the byte/row helpers `0x13050`, `0x130AC`, and `0x13188`.
It does not erase or program a PSoC application or FPGA image in this path.

**Verified:** Factory defaults include phantom off, speaker mode 1, output attenuation 20, output mute off, front-mic gain 30, and rate index 0.
Evidence: `0x205CC`, descriptor bytes `0x25EE4`, `0x25F1C`, `0x25F34`, `0x25F3C`, `0x26054`.
Replay applies the ordinary hardware handlers, so factory reset can change audible output and analog state (`0x15F58 → 0x16228`).

**Verified:** Factory reset does not directly clear the functional-mode byte or special gate.
The ADC enable through the panel hook is independent of the later EEPROM reset (`0x1F374`, `0x17004`).
Reports are reset as property data, but the diagnostic toggle mask resides elsewhere.
A later release can therefore report a mask that differs from the newly defaulted report value (`0x205CC`, `0x1F19C`).

**Verified:** Ordinary persistent settings still save while diagnostics is active.
A host gain change uses the ordinary property store, regardless of which ADC register `0x12F44` selects.
After a restart, that stored gain returns through the normal AGC path on newer hardware (`0x12D28`, `0x20D18`, `0x14A24`).
**Inferred:** Diagnostic mode itself is volatile, but changes made during it can survive a power cycle.

## Complete cluster function map

All behavior rows below are **Verified** unless they explicitly say **Unknown**.
The names file supplies one address/name/kind/evidence record per newly named function.
The four previously named entries appear here for continuity, but receive no duplicate name record.

### Input home and menu functions

| Address   | Name or role                                         | Exact evidence and limits                                                                                     |
| --------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `0x1DF30` | Existing input-home state builder, crosses `0x1E000` | Reads selected input and gain, configures gauge and widgets. Not a separate function at `0x1E000`.            |
| `0x1E0C0` | `PanelInputHome_LoadState`                           | Calls builder at `0x1E0C8`, then widget refresh at `0x1E0CE`.                                                 |
| `0x1E0D8` | `PanelInputHome_Update`                              | Redraws changed label at `0x1E0EC`, updates dirty gauge at `0x1E0F2`.                                         |
| `0x1E108` | `PanelInputHome_Draw`                                | Draws label/gauge and separator at `(2,44)`, width 156, color `0x9CD3`. Calls `0x1E110/116/12C`.              |
| `0x1E140` | `PanelInputHome_Clear`                               | Clears label, gauge, and separator through `0x1E158/15E/172`.                                                 |
| `0x1E184` | `PanelInputHome_OnCommand`, missing baseline entry   | Table `0x25C34` points to `0x1E185`. Command switch at `0x1E1A0..0x1E1AA`. Return at `0x1E31E`.               |
| `0x1E328` | `PanelInputHome_DrawInputLabel`                      | Maps selector through `0x21640`, draws resource `1C` or `1D` and digit at y=16. Calls `0x1E368/392`.          |
| `0x1E3E8` | Existing `PanelInput_SelectMenuItem`                 | Bounds selection against `0x1FFF8994`, changes highlight masks on label/value widgets.                        |
| `0x1E480` | `PanelInputMenu_GetSelection`                        | Returns `0x1FFF8F60`, return instruction `0x1E490`.                                                           |
| `0x1E498` | `PanelInputMenu_GetSelectedCommand`                  | Reads command byte of selected value widget, via menu map `0x1FFF8998`. No independent selection bound.       |
| `0x1E4D0` | Existing `PanelInput_FilterMenu`                     | Filters seven possible controls by input type, channel, and partner type. Writes menu bottom at `0x1FFF8F70`. |
| `0x1E768` | `PanelInputMenu_LoadState`                           | Calls filter at `0x1E770`, then widget refresh at `0x1E776`.                                                  |
| `0x1E780` | `PanelInputMenu_SelectorIsGuitar`                    | Maps selector, tests channels 10/11 at `0x1E798/79E`.                                                         |
| `0x1E7B0` | `PanelInputMenu_OnCommand`                           | Handles IDs 1 and `0x23`, updates layout and obsolete-area flags. Calls `0x1E80C/844`.                        |
| `0x1E868` | `PanelInputMenu_ClearObsoleteAreas`                  | Clears reduced column tails at `0x1E896/8B6`, plus guitar-transition rectangle at `0x1E8D8`.                  |
| `0x1E8F8` | `PanelInputMenu_DrawInputLabel`                      | Draws IN/G label and digit at y=0 through `0x1E938/962`.                                                      |
| `0x1E9B8` | `PanelInputMenu_Update`                              | Clears obsolete areas, redraws changed label, clears word `0x1FFF8F64`. Calls `0x1E9C0/9DE`.                  |
| `0x1E9F4` | `PanelInputMenu_Draw`                                | Clears obsolete areas, draws label, clears the same word. Calls `0x1E9FC/0x1EA00`.                            |
| `0x1EA14` | `PanelInputMenu_Clear`                               | Clears two menu columns and label through `0x1EA2E/44/58`.                                                    |

**Unknown:** Original purpose of word `0x1FFF8F64`.
The supplied decompile shows only zero stores in `0x1E9B8/0x1E9F4`, not a nonzero producer.
It is named explicitly as unresolved, not as an invented test-status flag.

### Gauge and popup functions

| Address   | Name or role                                       | Exact evidence and limits                                                                                              |
| --------- | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `0x1EA6C` | `PanelGauge_SetQueueAndStyle`                      | Stores queue at object `+0x1C`, style at `+0x19` (`0x1EA7E/84`).                                                       |
| `0x1EA90` | `PanelGauge_SetPosition`                           | Stores x/y at object `+0/+4` (`0x1EAA0/A6`).                                                                           |
| `0x1EAB4` | `PanelGauge_SetRangeAndSign`                       | Stores endpoints at `+8/+12`, sign style at `+0x18`. Only a changed first endpoint sets dirty (`0x1EAD0`).             |
| `0x1EAF0` | `PanelGauge_SetValue`                              | Changes value at `+0x10` and dirty word at `+0x14` only when the value differs.                                        |
| `0x1EB1C` | Existing `PanelGauge_ValueToFrame`                 | Clamps value between endpoints, handles reverse ranges, calculates a resource frame. Not an audio amplitude generator. |
| `0x1EBE0` | `PanelGauge_Update`                                | Calls `0x1EBFC` only when object `+0x14` is nonzero.                                                                   |
| `0x1EBFC` | Existing `PanelGauge_Draw`                         | Draws resource frames and digits, then clears dirty. Style table at RAM `0x1FFF8B4C`, flash `0x25E1C`.                 |
| `0x1F064` | `PanelGauge_Clear`                                 | Clears its rectangle with dimensions from the 20-byte style descriptor.                                                |
| `0x1F558` | `PanelPopup_SetActionState`                        | Stores action, value, and dirty flag at `0x1F57C/582/588`. No audio command dispatch.                                  |
| `0x1F5A0` | `PanelPopup_Update`                                | Tests dirty at `0x1F5AC`, clears it, calls content draw at `0x1F5B8`.                                                  |
| `0x1F5C8` | `PanelPopup_Draw`                                  | Draws four border rectangles, color `0x632C`, then content at `0x1F62A`.                                               |
| `0x1F638` | `PanelPopup_Clear`                                 | Clears `(4,45,152,59)` through `0x1F650`.                                                                              |
| `0x1F660` | `PanelPopup_DrawContent`                           | Uses 23 bitmap triples at `0x25E38`. Reads mute/main-mode/speaker state. Ends at `0x1F8C2`.                            |
| `0x1F8D8` | `PanelPopup_OnCommandNoOp`, missing baseline entry | Pointer `0x1F8D9` at `0x25E94`. Stack argument stores only, return `0x1F8FA`.                                          |

**Verified:** Popup triple fields are `[icon, nonzero-value text, zero-value text]`. Resource `0x7F` means no image.
The action bound is less than 23 (`0x1F660`).
Action 17 becomes action 14 or 15 according to active-speaker bit 1.
The popup displays pad actions. It does not itself execute mute, mono, dim, or guitar-mode commands.

### Functional-test functions

| Address   | Name                                        | Exact evidence and limits                                                                         |
| --------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `0x1F0C0` | `FunctionalTest_InitMode`                   | Clears only mode byte at `0x1F0C8`.                                                               |
| `0x1F0D8` | `FunctionalTest_Service`                    | Polls four encoders for mode 1, ordinary meters for mode 2. Calls `0x1F10A/12C/14E/170/178`.      |
| `0x1F188` | `FunctionalTest_SelectorPadPressNoOp`       | No diagnostic action. Return at `0x1F198`.                                                        |
| `0x1F19C` | `FunctionalTest_ToggleLEDOnRelease`         | Mode-1 check, mask toggle, LED write, report. No internal index bound. Known callers supply 0–13. |
| `0x1F210` | `FunctionalTest_EncoderPressNoOp`           | No diagnostic action. Return at `0x1F220`.                                                        |
| `0x1F224` | `FunctionalTest_ReportEncoderRelease`       | Mode-1 check and index ≤3. Report `[index,2,1]` at `0x1F25C`.                                     |
| `0x1F26C` | `FunctionalTest_OnModeCommand`              | Mode transition and ADC-mode operations. Command `0x51` bypasses the mode-equality check.         |
| `0x1F38C` | `FunctionalTest_ReportEncoderDelta`         | Signed 16-bit delta, eight-bit magnitude, report store, snapshot update at `0x1F3FC`.             |
| `0x1F408` | `FunctionalTest_ReportLEDMask`              | Two-byte little-endian mask, source-0 store at `0x1F434`.                                         |
| `0x1F444` | `FunctionalTest_DrawColorBars`              | Disable meter layouts, draw stripes and borders. No audio-signal synthesis.                       |
| `0x1FD48` | `PanelInputs_FirstSetBit16`, related helper | Scans bits 0–15, returns 16 for zero. Long-press caller at `0x1FD04`.                             |

### Indirect callback tables and missing functions

**Verified:** Each page descriptor contains widget pointer, widget count, then draw, update, clear, and command callback pointers.
The count is read as a byte. Each callback pointer includes the Thumb bit.

| Page RAM / initializer flash | Six 32-bit words, hexadecimal                           | Role         |
| ---------------------------- | ------------------------------------------------------- | ------------ |
| `1FFF8950 / 25C20`           | `1FFF88E4 00000006 0001E109 0001E0D9 0001E141 0001E185` | Input home   |
| `1FFF8B34 / 25E04`           | `1FFF8A54 0000000E 0001E9F5 0001E9B9 0001EA15 0001E7B1` | Input menu   |
| `1FFF8BB0 / 25E80`           | `00000000 00000000 0001F5C9 0001F5A1 0001F639 0001F8D9` | Output popup |

**Verified:** Indirect calls occur at `0x1CBFE`, `0x1CC46`, `0x1CCA2`, and `0x1CD02`, from offsets `+8/+12/+16/+20`.
These tables establish callable functions even when the baseline reports zero direct callers or omits the function entirely.

**Verified:** The recovered `0x1E184` callback uses 35 targets at `0x1E1B0..0x1E23B`, indexed by command minus one.

| ID                 | Thumb table value | Verified action                                                                   |
| ------------------ | ----------------- | --------------------------------------------------------------------------------- |
| `01`               | `0001E24F`        | Rebuild home state if the command channel equals the selected audio input.        |
| `02`               | `0001E26F`        | Update gauge from microphone gain only for the selected input in Mic mode.        |
| `03`               | `0001E2AB`        | Update gauge from instrument gain only for the selected input in Instrument mode. |
| `05`               | `0001E2E7`        | Rebuild microphone icon/state only for the selected input in Mic mode.            |
| `23`               | `0001E23D`        | Rebuild home state if selected-input value differs.                               |
| Other IDs `01..23` | `0001E31B`        | Return without a command-specific action.                                         |
| Outside `01..23`   | No table access   | Bound check at `0x1E1A2..0x1E1A4` branches to return.                             |

**Verified:** `0x1E1B0..0x1E23B` is data inside a function, not dozens of tiny branch functions.
Likewise, `0x1F8C4..0x1F8D7` is the preceding function's literal pool, not executable diagnostic logic.
The next function starts at `0x1F8D8`. Its descriptor pointer and return instruction establish its boundary.

## Safety notes

**Inferred:** Exit can apply encoder movement from the diagnostic interval to ordinary gain and attenuation.
The ordinary snapshots remain stale, as described above (`0x19444..0x1944E`, `0x19488..0x19494`).
Do not treat exit as an electrically neutral operation.

| Status   | Hazard                                                                                     | Evidence and limit                                                                                              |
| -------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| Verified | Diagnostic commands change real hardware, not just screens.                                | ADC writes `0x12FEC/0x1301C`, LED writes `0x12C20`. Do not invoke them on the device for discovery.             |
| Inferred | AGC changes can alter the microphone signal level.                                         | Compatible ADC semantics, pp26, 59–60. No mode-entry mute or gain-transfer sequence exists in `0x1F26C`.        |
| Verified | A rejected factory-reset value still enables AGC.                                          | `0x16F1E` guards only `0x17004`. Panel path `0x1F374` has no `0xAB` check.                                      |
| Verified | Factory reset changes persistent settings and replays hardware controls.                   | `0x16000`, `0x20F5C`, `0x20D18`. It can remove saved mute or attenuation preferences.                           |
| Inferred | EEPROM interruption can lose the previous settings image.                                  | One-copy write and final checksum patch in `0x20F5C`. No rollback transaction.                                  |
| Verified | Mode switches do not preserve all three mode variables as one unit.                        | `0x1F26C`, `0x12D28`, `0x19A34/58`. Same-mode requests cannot repair all inconsistent combinations.             |
| Verified | Diagnostic service does not block host audio commands.                                     | Main loop `0x1F986..0x1F9B2`, dispatcher `0x16228`. There is no exclusive test lock.                            |
| Verified | LED and encoder helpers rely on caller bounds.                                             | `0x1F19C`, `0x1F38C`, `0x12C20`. Do not expose these helpers as arbitrary host-index operations.                |
| Verified | I2C failure can block completion.                                                          | `0x11050` retries writes without an outer limit. No diagnostic timeout recovery surrounds the ADC or LED calls. |
| Unknown  | Physical LED current, ADC load, power-net identity, and audible transient size.            | Register writes cannot establish board-level electrical limits.                                                 |
| Verified | No application-flash or FPGA-flash write occurs in the isolated `0x50` transition handler. | Direct call graph `0x1F26C`. This does not make `0x51=AB` or independent update commands harmless.              |

## Validation and proposed tests

**Verified:** Static validation checked all 36 uncovered baseline addresses against the new TSV.
It also checked the two missing callback pointers, page descriptors, color bytes, report descriptors, and ADC-mode instruction calls.
The TSV contains 54 unique addresses, with 41 functions. Prettier and Markdownlint checks passed.
No new analysis script was necessary. Existing offline instruction tools cover this report.

Reproduce the instruction evidence without a device:

```sh
uv run --with capstone scripts/firmware/psoc-protocol-map.py 1f0c0 1f558
uv run --with capstone scripts/firmware/psoc-protocol-map.py 12fd0 13030
uv run --with capstone scripts/firmware/psoc-protocol-map.py 1e184 1e328
uv run --with capstone scripts/firmware/psoc-protocol-map.py 1f8d8 1f8fc
```

Risk: these commands read `flash.bin` and print instructions. Dependency installation can require network access.
The linear decoder also prints literal pools and switch tables as instructions. Use the code/table boundaries above.

| Status   | Unresolved question                                      | Proposed offline work                                                                                           |
| -------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Unknown  | Exact converter and microphone parts                     | Match an owner-supplied board photograph or schematic against the ADC3101 register evidence.                    |
| Unknown  | Applied PGA gain immediately after AGC disable           | Consult the exact part's transition specification. Do not substitute the saved gain value.                      |
| Unknown  | Role of `0x1FFF8F64`                                     | Trace all raw references beyond the supplied decompile. Keep the unresolved name until a producer exists.       |
| Unknown  | FPGA meter-control register and independent test signals | Inspect FPGA logic for `0x60800080`. Do not infer a sine generator from screen color bars.                      |
| Inferred | Report loss and mode-state inconsistencies               | Model simultaneous encoder events, same-mode requests, factory reset, rate changes, and update restore offline. |

No device test command is proposed. Never invoke functional-test commands on the device as part of this analysis.
