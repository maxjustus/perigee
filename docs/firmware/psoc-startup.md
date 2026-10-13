# PSoC startup, pins, and peripherals

The application configures 72 logical pins, four encoder counters, two SPI components, one fixed I2C controller, and five interrupt handlers.
The map below separates executable evidence from unresolved internal routes and external board connections.

## Scope and evidence

This report covers the application in `EnsemblePSoC.cyacd`, not the absent bootloader or an inspected circuit board.
No device access, firmware update, or shared Ghidra project change formed part of this analysis.

- **Verified** means an instruction, byte, or primary source establishes the stated fact.
- **Inferred** means the stated evidence supports a conclusion without a complete route or board trace.
- **Unknown** means the available evidence does not establish the fact.
- An address without a file name is a PSoC CPU address.
- `flash.bin` offset equals the flash address minus `0x10000`.
- `config.bin` offset equals the ECC address minus `0x48000000`.
- PSoC means Programmable System-on-Chip. ECC means error correction code.
- UDB means universal digital block. DSI means digital system interconnect.
- EMIF means external memory interface. GPIO means general-purpose input/output. SIO means special input/output.
- NVIC means nested vectored interrupt controller. ISR means interrupt service routine. IRQ means interrupt request.
- DMA means direct memory access. PHUB means peripheral hub. NVL means nonvolatile latch.
- IMO means internal main oscillator. ILO means internal low-speed oscillator. PLL means phase-locked loop.
- SPI means serial peripheral interface. I2C means Inter-Integrated Circuit. SRAM means static random-access memory.
- Register suffixes DR, PS, DM, BYP, BIE, and SLW mean output data, pin state, drive mode, bypass, bidirectional enable, and slew control.

### Input identity

| Input | SHA-256 |
|---|---|
| Vendor `EnsemblePSoC.cyacd` | `7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24` |
| `/tmp/apogee-fw/flash.bin` | `a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8` |
| `/tmp/apogee-fw/config.bin` | `7f6b8abed75862dd5ec93365dc972be00b7b133eaf6d6e3d94603dc8955e9479` |

**Verified:** All 355 vendor rows pass the additive checksum, declared length, flash-byte comparison, and ECC-byte comparison.
Each record contains 256 program bytes and 32 ECC-area bytes.
The vendor header is `2E12F0690000`.
Array 1 contains rows 0–255, array 2 contains rows 0–97, and array 3 contains row 255.
These facts derive directly from the vendor records, not the extraction script's fill values.

### Primary sources

| Source | Exact reference and use |
|---|---|
| CY8C52LP datasheet | [Infineon, document 001-84933 revision *P](https://www.infineon.com/assets/row/public/documents/30/49/infineon-psoc5lp-cy8c52lp-datasheet-datasheet-en.pdf). Printed pages 9, 20–23, 32–39, 46, 48, 96–97, 105. The PDF has a cover before printed page 1. |
| Creator startup | [Cm3Start.c](https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/Cm3Start.c), functions `Start_c`, `initialize_psoc`, `IntDefaultHandler`. |
| Creator fitter | [cyfitter_cfg.c](https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/cyfitter_cfg.c), lines 152–211, 230–286, 451–528. This is an example design, not Ensemble's configuration. |
| Register addresses | [cydevice_trm.h](https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/cydevice_trm.h). This is an address header, not a bit-field TRM. |
| Clock constants | [cydevice.h](https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/cydevice.h), `CYCLK_SRC_SEL_*`. |
| Cypress system library | [CyLib.c](https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/CyLib.c), [CyLib.h](https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/CyLib.h). PLL ratio, clock dividers, delays, and interrupt APIs. |
| Pin API | [cypins.h](https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/cypins.h), `CY_PINS_DM_*`, `CyPins_SetPinDriveMode`. |
| Counter API | [ClockCounter.c](https://raw.githubusercontent.com/tewtal/tasbot/d6cc8053429b7b099c186dd49c248ead29be347c/TASBot.cydsn/Generated_Source/PSoC5/ClockCounter.c), lines 37–123, 357–373. Fixed and UDB branches match the firmware's register sequence. |
| Interrupt component | [ClockCounter_IRQ.c](https://raw.githubusercontent.com/tewtal/tasbot/d6cc8053429b7b099c186dd49c248ead29be347c/TASBot.cydsn/Generated_Source/PSoC5/ClockCounter_IRQ.c), lines 104–117, `StartEx`. |
| I2C master API | [I2C_1_MASTER.c](https://raw.githubusercontent.com/SBannwarth/I2C/0892663dd73d4ba2f17f12279c170b90301add3e/I2C_FF.cydsn/Generated_Source/PSoC5/I2C_1_MASTER.c), lines 80–149, 196–266. Semantic match, with a different order of buffer-field stores. |
| I2C constants | [I2C_1.h](https://raw.githubusercontent.com/SBannwarth/I2C/0892663dd73d4ba2f17f12279c170b90301add3e/I2C_FF.cydsn/Generated_Source/PSoC5/I2C_1.h), configuration and state constants. |
| DMA startup comparison | [CyDmac.c](https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/CyDmac.c), `CyDmacConfigure`, and the conditional call in `Cm3Start.c`. |

The repository notes supply application context, not independent proof of silicon or register layouts.
All numerical maps below derive from the identified binary, with the primary sources above for register semantics.

## Memory map and reset path

### Silicon and address checks

| Status | Conclusion | Evidence and limit |
|---|---|---|
| Verified | The image identifies silicon `0x2E12F069`. | Vendor file header. |
| Inferred | The intended part is CY8C5268AXI-LP047, CY8C52LP family, 100-pin TQFP, 67 MHz maximum. | Datasheet printed p105, table 12-1, matches that ID exactly. No package inspection. |
| Verified | That part has 256 KiB flash, 64 KiB SRAM, 2 KiB EEPROM, 24 UDBs, four fixed timer blocks, and USB. | Datasheet p105, table 12-1. Do not substitute the 80 MHz CY8C58LP specification. |
| Verified | Flash occupies `0x00000000–0x0003ffff`. SRAM occupies `0x1fff8000–0x20007fff`. | Datasheet p23, table 5-5, agrees with the header and vector SP. |
| Verified | ECC-area bytes occupy `0x48000000–0x48007fff`. They are not ordinary flash addresses or an SRAM alias. | Datasheet p23. `0x21ad4` dereferences that window. |
| Verified | A flash row has 256 program bytes and 32 ECC/configuration bytes. | Datasheet p20 and all 355 vendor rows. |
| Verified | Application ECC data begins at offset `0x2000`, not offset zero. | Array 1 row 0 corresponds to global row 256. `256 × 32 = 0x2000`. The first address table is at `0x48002000`. |
| Unknown | Contents of absent rows, including the bootloader and its ECC bytes. | Array 0 has no record. Extraction fills absent flash with `ff` and absent ECC bytes with zero. Neither fill describes device contents. |
| Verified | The application uses external addresses under `0x60800000`. | `0x11754`, `0x12610`, `0x12658`. Datasheet p23 places these within EMIF's `0x60000000–0x60ffffff` window. |
| Inferred | `0x60800000` selects the FPGA through EMIF. | Application transactions and existing FPGA protocol map. It is not the EMIF controller register base. |
| Verified | The controller registers start at `0x40005400`. | Datasheet p23 and `0x21f20`. |

The generic Creator header agrees with the CY8C52LP datasheet for all address regions used here.
A header symbol alone does not prove that this part implements every named analog block.
No SC/CT analog block or digital filter block exists in the identified part, per datasheet p105.

### Application reset to main

| Status | Stage | Evidence |
|---|---|---|
| Verified | Flash words at `0x10000`: SP=`0x20008000`, reset=`0x10011`, NMI=`0x21969`, HardFault=`0x21969`. | `flash.bin[0:16]`. Handler pointers include the Thumb bit. SP is one byte beyond SRAM's upper address. |
| Verified | `Reset` at `0x10010` calls `Start_c` at `0x21970`. | Thumb branch at `0x10014`. The code after `0x10018` belongs to compiler support, not a reset safety loop. |
| Verified | `Start_c` processes one 16-byte region descriptor at `0x253c4`. | `0x21970`, descriptor words `0x253d8, 0x1fff8108, 0xdc8, 0x1b28`. |
| Verified | It copies 3528 bytes from `0x253d8–0x2619f` into `0x1fff8108–0x1fff8ecf`. | Copy loop in `0x21970`. |
| Verified | It clears 6952 bytes at `0x1fff8ed0–0x1fffa9f7`. | Zero loop in `0x21970`. No full-SRAM erase occurs. |
| Verified | It calls `__libc_init_array` at `0x25134`. | `0x21970`. Preinit range is empty. Constructor entries at `0x253ac/0x253b0` are `0x1003d/0x21a05`. |
| Verified | `initialize_psoc` at `0x21a04` creates 48 RAM vectors at `0x1fff8000`. | Copies the first four flash words, then installs `0x21969` for indices 4–47. |
| Verified | It writes AIRCR=`0x05fa0400`, sets CCR bit `0x200`, and selects VTOR=`0x1fff8000`. | `0x21a04`. Creator source identifies priority split and eight-byte exception-stack alignment. |
| Verified | It copies reset status from `PHUB_CFGMEM23_CFG1` into `0x1fff8104`. | `0x21a04`. It does not directly read `RESET_SR0` here. |
| Unknown | Who preserved that reset status, and the real hardware-reset path before application launch. | The bootloader is absent. `Reset` performs no such preservation. |
| Verified | It invokes `cyfitter_cfg` at `0x21ccc`, then clears `0x1fff8100`. | `0x21a04`. |
| Verified | `Start_c` invokes `main` at `0x1f8fc`. | `0x21970`. `main` never returns. |

**Verified:** The RAM table occupies `0x1fff8000–0x1fff80bf`.
The startup region copy does not overwrite it.
The default handler at `0x21968` loops forever, without an output shutdown sequence.

### Main initialization order

**Verified:** `main` enables global interrupts before the component initialization calls below (`0x1f8fc`).
The fitter previously disables them (`0x21ccc`).
This handoff depends on the inherited peripheral and NVIC state, not just the new vector contents.

| Order | Call | Verified action or scope |
|---|---|---|
| First | `0x10074` | Starts EMIF, DCFG0 clock, fixed I2C, both SPI components, EEPROM, fixed counter, and four encoder counters. |
| Next | `0x114fc`, inside `0x10074` | Writes control register A=`01`, control register B=`04`. Definitions follow below. |
| Next | `0x2014c`, `0x203b4`, `0x17540` | Initializes software timers, property state, and application state. |
| Next | `0x11754(1)` | Waits for FPGA identity/status. It precedes most application state and route setup. |
| Next | `0x132a4`, write `0x6080002d=1` | Initializes FPGA-related state, then writes the update/control flag. |
| Later | `0x1fa14`, `0x1feac` | Installs IRQ0, IRQ1, IRQ2, and IRQ6 handlers. I2C installs IRQ15 earlier. |
| Loop | `0x10168`, `0x144c0`, `0x20498`, `0x19390`, `0x1fa94`, `0x1ff6c`, `0x15668`, `0x20280` | Advances power/audio state, services UI and host work, and polls software timers. |

## Fitter configuration tables

**Verified:** `cfg_write_bytes32` at `0x21ad4` consumes exactly 44 address words.
For each word, its low byte is a pair count and its upper 24 bits form a base address.
Each two-byte record holds an offset and a value.
The destination is `base + offset`, not an address copied verbatim from the table.
The sample Creator fitter uses the same format.

| Status | Address | Contents and consumer |
|---|---|---|
| Verified | `0x25344` | Ten packed `{uint32 address, uint16 size}` zero descriptors, consumed by `0x21ccc`. |
| Verified | `0x25380` | Three packed `{uint32 destination, uint32 source, uint16 size}` copy descriptors. |
| Verified | `0x48002000–0x480020af` | 44 sparse address/count words. |
| Verified | `0x480020b0–0x480030c7` | 2060 offset/value pairs. Each evidence address below names the pair's offset byte. |
| Verified | `0x480030c8–0x48003147` | 128 bytes copied to `0x40010e00`, UDB B0/P7/U0 configuration. |
| Verified | `0x48003148–0x480031c7` | 128 bytes copied to `0x40011680`, UDB B1/P3/U1 configuration. |
| Verified | `0x480031c8–0x48003247` | 128 bytes copied to `0x40011880`, UDB B1/P4/U1 configuration. |
| Verified | `0x48003248–0x4800329f` | Nine ordered port configuration blocks, with alignment gaps. |

**Verified:** The ten zero ranges are:

| Destination | Length |
|---|---:|
| `0x400049c8` | 25 |
| `0x40004f00` | 24 |
| `0x40010000` | 3584 |
| `0x40010e80` | 384 |
| `0x40011400` | 640 |
| `0x40011700` | 384 |
| `0x40011900` | 768 |
| `0x40014000` | 2560 |
| `0x40014c00` | 512 |
| `0x40015000` | 32 |

Evidence: descriptors at `0x25344–0x2537f` and the loop at `0x21ccc`.
These are selected peripheral ranges, not a complete chip reset.

**Verified:** The fitter performs these phases in order (`0x21ccc`):

1. Disable global interrupts and set `MLOGIC_DEBUG |= 04`.
2. Apply the zero descriptors, then the three bulk copies.
3. Apply the 2060 sparse writes.
4. Write `USB_USBIO_CR1=20`, enable both route banks, and enable the UDB array.
5. Copy the nine port blocks in the order below.
6. Write UDB CFG27 overrides, then configure clocks, cache, wait pipeline, and analog defaults.
7. Copy 14 active-power bytes into the alternate-active power registers.

The CFG27 overrides are B0/P0/U1=`84`, B0/P2/U1=`c4`, and B1/P2/U1=`84`.
Their raw values are **Verified** at `0x21ccc`. Their complete logic-level consequences remain **Unknown**.

### Sparse table coverage

**Verified:** The table programs timer, port, UDB, DSI, and interrupt-mux registers.
The decoder emits every pair with its source address and available register name.

| Destination pages | Pair counts in page order | Evidence |
|---|---|---|
| `40004500, 40004f00, 40005200, 40005400, 40006400, 40006500` | `1,4,11,1,9,3` | Address words `48002000–48002014` |
| `40010000–40010f00`, stride `100` | `110,68,107,77,98,76,77,75,88,78,79,80,76,74,50,62` | `48002018–48002054` |
| `40011400–40011b00`, stride `100` | `60,86,52,81,32,78,84,79` | `48002058–48002074` |
| `40014000–40014900`, stride `100` | `7,8,22,14,9,17,12,12,23,34` | `48002078–4800209c` |
| `40014c00,40014d00,40015000,40015100` | `21,15,8,2` | `480020a0–480020ac` |

**Unknown:** A complete DSI netlist and programmable-logic equations.
Nonzero route bytes establish configuration, not the identity or polarity of the board signal at either endpoint.

## Clock tree and timer units

| Status | Clock or control | Value and derivation | Evidence |
|---|---|---|---|
| Verified | IMO | 3 MHz, internal source, no doubler. `FASTCLK_IMO_CR=03`, factory 3 MHz trim copied. | `0x21b90–0x21b9e`, `CyLib.h` IMO constants. |
| Verified | PLL input | IMO. `CLKDIST_CR=08`, source bits `1:0=0`. | `0x21b88–0x21b8e`, `CyPLL_OUT_SetSource`. |
| Verified | PLL ratio | P=`66`, Q register=`2`, actual Q=`3`. | Halfword store `0x0242` at `0x21ba6`, `CyLib.c:197–198`. |
| Inferred | PLL frequency | Nominal `3 MHz × 66 / 3 = 66 MHz`. | Verified register ratio, not an instrument measurement. |
| Verified | PLL startup | Configuration `1251`, two consecutive lock samples, maximum 25 iterations, 480-cycle delay per iteration. | `0x21ba8–0x21bf8`. Exhaustion enters `CyClockStartupError(3)` at `0x21ac8`. |
| Verified | Master | PLL source, final divider zero. | `0x21bfc–0x21c1a`. |
| Inferred | Master frequency | 66 MHz nominal. | `CyMasterClk_SetDivider` defines divisor as register plus one. |
| Verified | Bus | Divider low byte=`1`, configuration=`08`. | `0x21c0a–0x21c14`. The high divider byte is not written here. |
| Inferred | Bus/CPU frequency | 33 MHz nominal with the expected zero high divider byte. Delay constants independently encode 33 MHz. | `0x21b48`, initialized RAM `0x1fff8ec0=33000`, `0x1fff8ec4=33`. Bootloader high-byte state is absent. |
| Verified | DCFG0 | Divider=`6`, mode/source=`18`. | `0x21b4e–0x21b58`. Source zero is synchronous digital clock. |
| Inferred | DCFG0 frequency | `33 MHz / 7 ≈ 4.714286 MHz`. | Clock source and divider, conditional on nominal bus clock. Destination route unresolved. |
| Verified | DCFG1 | Divider=`2`, mode/source=`18`. | `0x21b5a–0x21b64`. |
| Inferred | DCFG1 frequency | 11 MHz nominal. | Same source rule. Destination route unresolved. |
| Verified | DCFG2 | Divider=`499`, mode/source=`19`. | `0x21b66–0x21b72`. Source one is IMO. |
| Inferred | DCFG2 frequency | 6 kHz nominal. | `3 MHz / 500`. Destination route unresolved. |
| Verified | DCFG3 | Divider=`2999`, mode/source=`19`. | `0x21b74–0x21b80`. |
| Inferred | DCFG3 frequency | 1 kHz nominal. | `3 MHz / 3000`. |
| Verified | ILO | `SLOWCLK_ILO_CR0=02`. | `0x21b82–0x21b86`. No application watchdog service was identified. |
| Verified | Digital clock enable | `PM_ACT_CFG2 |= 0f`, then active state copied into alternate-active state. | `0x21c22–0x21c30`, `0x21ccc`. |

**Verified:** The application writes no crystal startup sequence in `ClockSetup`.
External audio clocks do not define the CPU clock in this routine.

**Verified:** `CyDelayCycles` is `0x23a60`, `CyDelay` is `0x23ad4`, and `CyDelayUs` is `0x23b18`.
The initialized delay constants occupy flash `0x26190–0x2619b` and RAM `0x1fff8ec0–0x1fff8ecb`.
`CyDelayUs` takes a 16-bit argument.
At `0x100ec`, arguments `6000`, `5`, and `2` therefore mean microseconds, not milliseconds.

### Timestamp API requested by the audio analysis

| Status | Function | Meaning |
|---|---|---|
| Verified | `0x23154` | Creator Counter initialization for fixed TMR0. Period and counter=`ffff`, interrupt mask zero. |
| Verified | `0x23238` | Starts that counter. `PM_ACT_CFG3` bit 0 and `TMR0_CFG0` bit 0 become set. |
| Verified | `0x232bc` | Reads `TMR0_CNT_CMP0` to force capture, then returns `TMR0_CAP0`. It is `Counter_ReadCounter`, not a free-running RAM tick. |
| Verified | `0x20364` | Returns `~Counter_ReadCounter()` as a 16-bit value. |
| Verified | `0x20378` | Returns `now-start`. If `now < start`, it subtracts one more, modulo 65536. |
| Inferred | Timer units | One millisecond per count. DCFG3 supplies a 1 kHz candidate clock, and software uses thresholds 500, 750, and 3000. |
| Unknown | Exact clock route | The DSI-to-TMR0 clock route is not decoded. The 1 ms unit is not an electrical measurement or a fully traced net. |

**Verified:** Sparse pairs `0x480020b2/0x480020b4` initialize `TMR0_CFG1=30` and `TMR0_RT0=4b`.
Pairs `0x480020b6/0x480020b8` initialize `TMR1_CFG1=80` and `TMR1_RT0=4b`.
The application has no identified TMR1 Start call or TMR1 ISR.

**Inferred:** A complete 16-bit timer cycle is 65.536 seconds at the inferred 1 kHz rate.
The elapsed helper loses one count across wrap (`0x20378`), and cannot distinguish multiple wraps.
Do not convert its thresholds into guaranteed wall-clock durations before the clock route is established.

## Configured pin map

### Reset state is not the fitted state

**Verified, datasheet p39:** Active reset holds I/O in analog high impedance.
After release, hardware applies per-port NVL reset configuration.
**Unknown:** This unit's NVL values and bootloader pin actions.
The `.cyacd` rows do not supply the four device-configuration NVL bytes.

**Verified, datasheet p21:** NVLs control port reset modes, debug access, optional P1[2] reset, boot clock, and ECC use.
**Inferred:** ECC is disabled for configuration storage because the application consumes structured data in the ECC area.
The actual `ECCEN` NVL bit is not present in these inputs.

The tables below describe writes from `cyfitter_cfg`, not voltages during hardware reset or the bootloader.
A configured drive mode does not identify the connected circuit.

### Whole-port values

All entries in this table are **Verified** bytes from the indicated copy source.
A dash means no write in that port block, not a zero register or a low pin.
`PS=00` in a copy is a write to a read-only field, not evidence that input pins read low.

| Port | ECC source | DR | DM0/DM1/DM2 | SLW | BYP | BIE | INP_DIS | Final byte |
|---|---|---:|---|---:|---:|---:|---:|---|
| P0 | `48003248`, 8 bytes | — | `00/ff/ff` | `00` | `00` | `00` | `00` | CTL=`02` |
| P12 | `48003250`, 10 bytes | `cc` | `00/fc/33` | `00` | `33` | `00` | `00` | SIO_HYST_EN=`00` |
| P15 | `4800325c`, 10 bytes | `00` | `dc/3f/23` | `00` | `ff` | `00` | `00` | CTL=`00` |
| P1 | `48003268`, 10 bytes | `c0` | `24/e0/00` | `00` | `20` | `00` | `00` | CTL=`00` |
| P2 | `48003274`, 8 bytes | — | `b8/77/47` | `00` | `77` | `00` | `00` | CTL=`00` |
| P3 | `4800327c`, 10 bytes | `c7` | `28/d7/11` | `00` | `11` | `00` | `00` | CTL=`00` |
| P4 | `48003288`, 8 bytes | — | `00/ff/ff` | `00` | `00` | `00` | `00` | CTL=`04` |
| P5 | `48003290`, 8 bytes | — | `00/ff/ff` | `00` | `00` | `00` | `00` | CTL=`06` |
| P6 | `48003298`, 8 bytes | — | `00/ff/ff` | `00` | `00` | `ff` | `00` | CTL=`0a` |

**Verified:** All copied slew bytes are zero.
**Verified, datasheet p37:** This selects fast slew where the pin supports slew control.
**Verified:** P6 alone has all eight bidirectional-enable bits set in these blocks.

**Inferred:** P0, P4, P5, and P6 implement the EMIF address/data groups.
Evidence is their nonzero port CTL selections, P6 bidirectional mask, and the active EMIF byte-access path.
**Unknown:** Exact CTL bit-field decoding and each group's A[n]/D[n] order.
Do not substitute a guessed address/data pin assignment for the raw port selections above.

### Package pad numbers

All pad numbers are **Verified** for the datasheet's 100-pin TQFP, printed p9, figure 2-4.
Their application to this board is **Inferred** from the image silicon ID, not a package inspection.
Within each list, entries correspond to logical bits 0 through 7.

| Port | TQFP pads for bits 0–7 | Supply domain |
|---|---|---|
| P0 | `71,72,73,74,76,77,78,79` | VDDIO0 |
| P1 | `20,21,22,23,24,25,27,28` | VDDIO1 |
| P2 | `95,96,97,98,99,1,2,3` | VDDIO2 |
| P3 | `44,45,46,47,48,49,51,52` | VDDIO3 |
| P4 | `69,70,80,81,82,83,84,85` | VDDIO0 |
| P5 | `16,17,18,19,31,32,33,34` | VDDIO1 |
| P6 | `89,90,91,92,6,7,8,9` | VDDIO2 |
| P12 | `53,54,67,68,4,5,29,30` | Bits 0–1: VDDIO3. Bits 2–3: VDDIO0. Bits 4–5: VDDIO2. Bits 6–7: VDDIO1. |
| P15 | `42,43,55,56,93,94,35,36` | Bits 0–3: VDDIO3. Bits 4–5: VDDIO2. Bits 6–7: VDDD. |

Supply associations are **Verified** in datasheet p9, table 2-1.
**Unknown:** Actual board voltages on all five supply domains.

### Per-pin function and electrical state

The DM and BYP decode is **Verified** from the port bytes and datasheet pp34–37.
BYP zero selects DR. BYP one selects a digital-system signal for ordinary GPIO/SIO pins.
A nonzero EMIF CTL overrides the simple GPIO interpretation.
Every external board connection below remains **Unknown**, except the inferred FPGA bus association.

| Pins | Configured function and state | Evidence | Board connection or limit |
|---|---|---|---|
| P0[0:7] | DM6 strong, EMIF selector `02`, BIE zero | `48003248–4f` | Inferred EMIF group. Exact signal order unknown. |
| P1[0], P1[1], P1[3], P1[4] | DM0 analog high impedance | `4800326a–6c` | Debug-capable pins. Actual debug override/NVL state unknown. |
| P1[2] | DM1 digital high impedance | Same | Optional reset capability does not prove reset use. |
| P1[5] | DM3 resistive pull-down mode, BYP one | `4800326a–6e` | DSI drives it. It can drive strongly high. Net unknown. |
| P1[6:7] | DM2 resistive pull-up, DR one, BYP zero | `48003268–6e` | Weak high at fitted state. Input role and circuit unknown. |
| P2[0:2] | DM6 strong, BYP one | `48003274–78` | DSI output signals unknown. |
| P2[3] | DM1 digital high impedance, BYP zero, synchronized input, PICU type one | `48003274–78`, `480020b0`, `480020c0` | Inferred FPGA interrupt line through IRQ6 ISR. |
| P2[4:5] | DM3 resistive pull-down mode, BYP one | `48003274–78` | DSI signal can select strong high. Not necessarily passive inputs. |
| P2[6] | DM6 strong, BYP one | Same | DSI output unknown. |
| P2[7] | DM1 digital high impedance, BYP zero | Same | Input role unknown. |
| P3[0] | DM6 strong, BYP one | `4800327e–82` | DSI output unknown. DR bit one does not establish output level. |
| P3[1:2] | DM2 pull-up, DR one, BYP zero | `4800327c–82` | Weak high. Signal identity unknown. |
| P3[3] | DM1 digital high impedance, DR zero, BYP zero | Same, `0x2200c`, `0x22048` | Software-controlled pin. Runtime strong-high mode is described below. |
| P3[4] | DM6 strong, BYP one | Same | DSI output unknown. |
| P3[5] | DM1 digital high impedance, DR zero, BYP zero | Same | Input role unknown. |
| P3[6:7] | DM2 pull-up, DR one, BYP zero | Same | Weak high. Signal identity unknown. |
| P4[0:7] | DM6 strong, EMIF selector `04` | `48003288–8f` | Inferred EMIF group. Exact signal order unknown. |
| P5[0:7] | DM6 strong, EMIF selector `06` | `48003290–97` | Inferred EMIF group. Exact signal order unknown. |
| P6[0:7] | DM6 strong, EMIF selector `0a`, BIE one | `48003298–9f` | Inferred EMIF bidirectional data group. Exact signal order unknown. |
| P12[0:1] | DM4 open-drain low, BYP one | `48003252–56` | Inferred I2C SCL/SDA pair. Datasheet p9 identifies SCL at bit 0, SDA at bit 1. DSI route not decoded. |
| P12[2:3] | DM2 pull-up, DR one, BYP zero | `48003250–56` | Weak high. Signal identity unknown. |
| P12[4:5] | DM6 strong, BYP one | Same | Not the configured open-drain pair. Dedicated I2C capability alone does not prove I2C use. |
| P12[6:7] | DM2 pull-up, DR one, BYP zero | Same | Weak high. Signal identity unknown. |
| P15[0:1] | DM6 strong, BYP one | `4800325e–62` | Digital outputs, not proof of an external crystal. |
| P15[2:4] | DM3 resistive pull-down mode, BYP one | Same | DSI signals unknown. No proof of a 32 kHz crystal. |
| P15[5] | DM6 strong, BYP one | Same | DSI output unknown. |
| P15[6:7] | USBIO special case. Fitter writes `USB_USBIO_CR1=20`. | `0x21ccc`, datasheet pp35,37 | Effective drive state unknown. Ordinary DM1 decode is invalid for USBIO. |

**Verified, datasheet p37:** Port-wide writes do not configure USBIO drive-mode bits.
The raw P15 DM bytes therefore cannot establish digital high impedance on P15[6:7].
These pins also support USB and alternate debug functions. No USB Start call was identified in this application.

### Pin route selector bytes

All values are **Verified** sparse-table writes. Exact selected DSI net identities remain **Unknown**.

| Port | OUT_SEL0 | OUT_SEL1 | DBL_SYNC_IN | Pair addresses |
|---|---:|---:|---:|---|
| P1 | No write | No write | `c4` | `480020ba` |
| P2 | `64` | `56` | `08` | `480020bc,be,c0` |
| P3 | `10` | `01` | `e6` | `480020c2,c4,c6` |
| P12 | `22` | No write | `cf` | `480020c8,ca` |
| P15 | `55` | `66` | No write | `480020cc,ce` |

The fitter does not explicitly zero every port mux register.
Unwritten register values require the reset specification or the bootloader state.

### Software GPIO and UDB control registers

| Status | API/address | Established behavior |
|---|---|---|
| Verified | `0x2200c` | Writes P3[3] DR with a port read/modify/write. |
| Verified | `0x22048` | Changes P3[3] drive bits through `PRT3_PC3`. Creator drive-mode arguments are shifted left by one. |
| Verified | `0x10514(0)` | Calls SetDriveMode(`02`), then Write(0). This is digital high impedance, not resistive pull-up. |
| Verified | `0x10514(nonzero)` | Calls SetDriveMode(`0c`), then Write(1). This is strong output high. |
| Inferred | P3[3] transition risk | Strong mode precedes the high data write. A prior zero latch permits a brief strong-low interval. No board consequence is established. |
| Verified | `0x22a6c` | Writes `B0_UDB10_CTL`, address `0x4000647a`. Label here: control register A. |
| Verified | `0x22d5c` | Writes `B0_UDB06_CTL`, address `0x40006476`. Label here: control register B. |
| Verified | `0x222f8` | Writes `B1_UDB05_CTL`, address `0x40006575`. Display SPI helper selects values 0, 1, 2, or 3. |
| Verified | Fitter control values | ECC pairs `480020d4` and `480020d2` set A=`09`, B=`04` before main. |
| Verified | Application control values | `0x114fc` sets RAM shadows `0x1fff810c=01`, `0x1fff810d=04`, then writes A and B. |
| Verified | `0x1152c`, `0x11578` | Set or clear a caller-supplied mask in the A or B shadow, then write the whole register. |
| Unknown | A/B physical endpoints | No complete route from UDB control bits to port pads was recovered. A control-register byte is not a port byte. |

**Verified:** `0x100ec` clears A masks `10` and `02`, sets B mask `02`, waits 6000 µs, then sets B mask `01`.
It clears A mask `02`, waits 5 µs, sets A mask `02`, and waits 2 µs.
**Unknown:** Which external supplies, resets, relays, or enables these masks control.
Do not attach a supply name or safe polarity solely from that sequence.

## Peripheral map

| Status | Component | Hardware and APIs | Role and uncertainty |
|---|---|---|---|
| Verified | EMIF | Init `21f20`, Enable `21f60`, Start `21fb8`. `NO_UDB=1`, `EM_TYPE=1`, read/write wait-state registers=`1`, memory-clock divider=`0`. | Byte transactions to FPGA window established at `12610/12658`. Exact bus pin netlist unresolved. |
| Verified | Fixed I2C master | Init `22318`, Enable `2237c`, Start `223c0`, ISR `223ec`, WriteBuf `2278c`, ReadBuf `22898`. | `CFG=06`, `XCFG=81`, divider low=`15`, high=`00`, IRQ15 priority 7. |
| Inferred | I2C pin pair | P12[0:1], SCL/SDA in that order | The only fitted open-drain-low pair, plus datasheet p9. Master-mode DSI can use other pins, per p48. |
| Unknown | I2C electrical rate | The divider value is verified. The exact rate needs the block's divider formula and source confirmation. | Do not equate register `15` with 15 Hz, 21 Hz, or a software delay. |
| Inferred | Preamp SPI, 16-bit | Start `221cc`, Init `2213c`, Enable `2216c`, WriteTxData `22244`. Datapath B0 UDB14/15. | `108bc` constructs a 16-bit command and polls TX status. Pin-level SCLK/MOSI/MISO/select assignment unresolved. |
| Verified | Preamp SPI registers | TX status B0_UDB15_ST, RX status B0_UDB14_ST, TX FIFO B0_UDB14_F0, RX FIFO B0_UDB14_F1. | `22204`, `22224`, `22244`, `22278`. Status-control mask at B0_UDB13_MSK=`1f`. |
| Inferred | Display SPI, 8-bit | Start `22b1c`, Init `22a8c`, Enable `22abc`, WriteTxData `22b94`. Datapath B1 UDB09. | `10958/10988/109dc` pass display command/data bytes and select B1_UDB05_CTL values. |
| Verified | Display SPI registers | TX status B0_UDB10_ST, RX status B0_UDB09_ST, TX/RX FIFOs B1_UDB09_F0/F1. | `22b54`, `22b74`, `22b94`, `22bc8`. Status-control mask B0_UDB12_MSK=`0f`. |
| Verified | Fixed counter | TMR0, Counter_Start `23238`, ReadCounter `232bc`, period=`ffff`. | Poll-based scheduler. No counter ISR assignment. |
| Verified | TMR1 configuration | Fitter initializes CFG1=`80`, RT0=`4b`. | `480020b6/b8`. Runtime role unknown. No identified Start or ISR. |
| Inferred | Four quadrature decoders | Four signed 16-bit positions centered on `8000`, polled from the main UI path. | Counter-backed wrappers `22dec`, `22ea0`, `22f54`, `23008`. Physical encoder pins unresolved. |
| Verified | EEPROM component | Start `23058` calls `CyEEPROM_Start` at `23a80`. Write path `23064` sends 16-byte rows to the supervisory controller. | Fitted storage path, not evidence of a DMA channel. |
| Verified | Analog default helper | `21c88` copies factory bandgap trim and writes `PUMP_CR0=44`. | No ADC acquisition or DAC output Start call identified in startup. Board audio converters are external. |
| Unknown | Other UDB logic | Fitter configures all 24 physical UDB sites. | A UDB can contain multiple functions. The map below does not claim exclusive ownership. |

The SPI and quadrature component names describe inferred function, not recovered original component instance names.
The I2C and Counter API suffixes match public Creator code semantics.
The linked public I2C source differs in store order, so this report does not claim a byte-identical library version.

### Encoder resource map

Register ownership below is **Verified** from the listed functions.
The named front-panel role is **Inferred** from the UI consumer at `0x19390`.
Every physical phase-A/phase-B pin and direction polarity remains **Unknown**.

| Inferred role | Start / GetCounter | Counter Start / ReadCounter | Datapath pair | Counter control / status | Decoder status |
|---|---|---|---|---|---|
| Speaker level | `22dc0 / 22dec` | `2344c / 234c4` | B1 UDB06/07 | B1_UDB04_CTL / B1_UDB05_ST | B1_UDB04_ST |
| Input selection/gain | `22e74 / 22ea0` | `235f8 / 23670` | B0 UDB00/01 | B0_UDB07_CTL / B0_UDB01_ST | B0_UDB00_ST |
| Headphone 1 level | `22f28 / 22f54` | `237a4 / 2381c` | B0 UDB02/03 | B1_UDB07_CTL / B0_UDB03_ST | B0_UDB07_ST |
| Headphone 2 level | `22fdc / 23008` | `23950 / 239c8` | B0 UDB04/05 | B0_UDB11_CTL / B0_UDB05_ST | B1_UDB11_ST |

Each wrapper starts a counter, writes `8000`, and returns `int16(raw-8000)`.
Each UDB Counter initializer writes period, initial count, and compare=`8000`, then sets interrupt mask zero.
The decoder mask is `0f`, but no NVIC handler for an encoder is installed.

### DMA boundary

**Verified:** `initialize_psoc` contains no `CyDmacConfigure` call after `cyfitter_cfg`.
Public `Cm3Start.c` makes that call conditional on `DMA_CHANNELS_USED__MASK0 != 0`.
**Inferred:** This application uses no Creator DMA component.

**Verified:** The analyzed functions contain no identified DMA channel enable or transfer-descriptor setup.
The fitter's decoded destinations do not configure PHUB DMA descriptors.
The read of `PHUB_CFGMEM23_CFG1` at `0x21a04` preserves reset status. It does not start channel 23.

**Unknown:** DMA state inherited from the absent bootloader.
The FPGA's PCIe audio DMA is a separate engine and is not PSoC DMA.

## Interrupt and ISR assignments

All vector addresses, handler pointers, priorities, and enable masks below are **Verified** application writes.
Logical IRQ numbers differ from vector indices by 16.
Priority bytes equal the API priority shifted left by five.

| IRQ / vector index | RAM vector word | Handler | Priority / byte | Installer | Established behavior |
|---|---|---|---|---|---|
| 0 / 16 | `1fff8040` | `1f9b8`, pointer `1f9b9` | 5 / `a0` | `1fa14 → 22c24` | Sets flag `1fff8f88`, increments `1fff8f94`, disables IRQ0. Main services I2C device `70`, then enables IRQ0. |
| 1 / 17 | `1fff8044` | `1f9dc`, pointer `1f9dd` | 5 / `a0` | `1fa14 → 22cc0` | Sets flag `1fff8f8c`, increments `1fff8f98`, disables IRQ1. Main services I2C device `71`, then enables IRQ1. |
| 2 / 18 | `1fff8048` | `1fa00`, pointer `1fa01` | 7 / `e0` | `1fa14 → 23310` | Sets `1fff8f90`, disables IRQ2. Main calls `17660`, then enables IRQ2. |
| 6 / 22 | `1fff8058` | `1fd84`, pointer `1fd85` | 4 / `80` | `1feac → 220a0` | Clears P2[3] PICU status, services FPGA event bits 0,1,2,3,5. |
| 15 / 31 | `1fff807c` | `223ec`, pointer `223ed` | 7 / `e0` | `22318 → 23b3c` | Fixed I2C master state machine. Uses CSR, data, master-control, and buffer state. |
| Other IRQs 3–5,7–14,16–31 | Corresponding words in the 48-entry table | `21968`, pointer `21969` | Not explicitly set here | `21a04` | Infinite-loop default handler. No application assignment identified. |
| Core exceptions except reset | NMI/HardFault from flash, all later exception slots initialized in RAM | `21968` | Not explicitly set here | `21a04` | No separate SysTick, SVC, PendSV, or fault recovery handler identified. |

**Inferred:** IRQ0 and IRQ1 are front-panel I2C expander notifications, from their deferred device reads at `0x1fa94`.
**Unknown:** Their exact DSI input pins and whether additional logic filters those inputs.
**Inferred:** IRQ2 is an application power/event request, from its deferred `0x17660` call.
Its exact electrical source remains **Unknown**.

**Verified:** Sparse configuration writes `IDMUX_IRQ_CTL0=bf` and `IDMUX_IRQ_CTL3=c0` at pairs `480030c4/480030c6`.
**Unknown:** A fully decoded interrupt-mux route and edge/level mode for every software IRQ.
Do not infer a physical pin from a software IRQ number.

**Verified:** P2[3] is the only explicit sparse PICU type write: `PICU2_INTTYPE3=1` at pair `480020b0`.
`0x22080` reads the entire `PICU2_INTSTAT`, then returns bit 3.
**Inferred:** The read can acknowledge other port-2 pin events because the status register has port scope.
The datasheet establishes the shared PICU structure on p38. Exact clear semantics require the register TRM.

**Verified:** IRQ6 priority is numerically lower than IRQ0/1 and IRQ2/15.
`initialize_psoc` writes the Creator priority-group encoding `0x400` in AIRCR.
Retain that encoding unless the replacement explicitly defines a different exception-priority policy.

## Safety notes

| Status | Risk | Required constraint |
|---|---|---|
| Verified | The image lacks the bootloader, NVLs, and actual reset-release pin state. | Preserve recovery access. Do not replace the bootloader or NVLs from this map. Evidence: absent array 0, datasheet p21. |
| Verified | The identified SKU is rated at 67 MHz, not 80 MHz. | Retain the nominal 66 MHz PLL and 33 MHz bus until a validated clock design exists. Evidence: p105, `21b48`. |
| Verified | EMIF specifications limit bus clock to 33 MHz. | Do not raise the bus to the PLL frequency. Evidence: datasheet pp96–97. |
| Verified | A=`09` before main differs from A=`01` after `114fc`. | Preserve the transition order until each control bit's physical effect is known. |
| Inferred | Direct GPIO replacements for UDB outputs can invert a power/reset signal or create a glitch. | Keep untraced hardware control outputs unchanged. Evidence: BYP masks and unresolved routes. |
| Verified | Pull-up mode drives strongly low for data zero. Pull-down mode drives strongly high for data one. | Do not treat these modes as unconditional weak bias. Evidence: datasheet p36, table 6-6. |
| Verified | P6 has bidirectional-enable bits and strong drive mode. | Preserve hardware output-enable behavior. Permanent output mode can contend with the FPGA. Evidence: `48003298–9f`. |
| Verified | P12[0:1] uses open-drain-low mode. | Do not replace the inferred I2C pair with push-pull outputs. Check external pull-up voltage first. Evidence: p48 and `48003252–56`. |
| Unknown | Supply voltages and external loads. | Do not assume every port tolerates the same voltage. Use the supply-domain map and a board schematic. |
| Verified | GPIO overvoltage current limit differs from SIO behavior. | Limit GPIO clamp current to 100 µA where the datasheet permits it. Evidence: p39. |
| Inferred | P3[3] can pulse low before strong high because drive mode changes first. | Establish the attached circuit and safe polarity before a replacement changes this order. Evidence: `10514`. |
| Verified | USBIO drive semantics differ from GPIO. | Do not apply generic DM decode to P15[6:7]. Evidence: datasheet p37. |
| Verified | PLL error and unexpected interrupts enter infinite loops. | Add no unproven output shutdown writes. A safe shutdown requires actual control-net polarity. Evidence: `21ac8`, `21968`. |
| Verified | The software timer helper miscounts one tick across wrap. | Preserve compatibility or correct it with tests and explicit interval limits. Evidence: `20378`, `20280`. |
| Verified | Delay APIs use different units. | Keep `100ec` delays in microseconds. A 1000-fold error changes hardware sequencing. Evidence: `23b18`, `23ad4`. |
| Verified | Fitter copies configure pads before application power initialization. | A replacement must consider reset, bootloader, fitter, and main as four separate electrical states. Evidence: `21ccc`, `10074`. |
| Verified | Flash/ECC data share programming rows. | Preserve all 288 bytes per row during compatible updates. Do not treat ECC bytes as disposable checksums. Evidence: p20, vendor records. |
| Verified | EEPROM/flash writes can take 20 ms, and reset can corrupt data. | Prevent reset during nonvolatile writes. Evidence: datasheet p20, supervisory write path `23064`. |

## Proposed tests and unresolved work

### Reproducible static checks

Run the decoder without a device:

```sh
python3 scripts/firmware/psoc-startup-decode.py /tmp/apogee-fw
```

The decoder emits hashes, vectors, the RAM descriptor, all sparse writes, copy descriptors, and raw pin-register values.
It models explicit table writes only. It does not simulate reset values, read-only registers, USBIO, or peripheral side effects.
Its `drive_modes` numbers are raw three-bit fields. They are not a valid USBIO mode decode.

Check the script without device access:

```sh
python3 -B -c 'import ast,pathlib; ast.parse(pathlib.Path("scripts/firmware/psoc-startup-decode.py").read_text())'
```

These commands have no device or flash risk. They read local analysis files and print results.

Validation passed for normal/optimized output parity, known decoded values, seven malformed-input cases, and all 162 TSV records.
The decoder also passed Python syntax checks and Ruff format/lint checks.
The malformed-input tests cover short/long images, invalid copy sources, invalid copy lengths, and a wrong sparse-table endpoint.

### Remaining evidence requirements

| Unknown | Next evidence | Risk |
|---|---|---|
| TMR0 clock source and exact timestamp unit | Decode the DSI clock endpoint and `TMR0_RT0=4b` against the register TRM. | Static analysis only. No device risk. |
| EMIF A[n]/D[n]/control pin identities | Decode port CTL fields and DSI outputs against the architecture/register TRM. | Static analysis only. |
| A/B control-bit endpoints | Trace B0_UDB10_CTL and B0_UDB06_CTL through UDB logic and DSI to pads. | Static analysis only. |
| Pin-to-board nets and safe polarities | Obtain schematics or inspect an unpowered board under a separate owner-approved procedure. | Physical inspection can damage the unit. No powered test is authorized here. |
| NVLs and bootloader handoff | Obtain an existing read-only archival image or vendor source. | No readback command is proposed. Debug attachment can reset the part or alter pad behavior. |
| USBIO effective state | Obtain NVL/bootloader state and decode USBIO-specific registers. | Static evidence first. Do not test with a generic GPIO write. |

No live test command is proposed because no established read-only interface exposes these internal routes or pad voltages safely.
The missing route and board evidence prevents a claim that this map alone is sufficient for safe replacement firmware.
