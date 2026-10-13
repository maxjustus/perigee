# PSoC audio hardware control

The firmware controls analog paths through SPI, three audio I2C addresses, and byte registers in the FPGA.

## Scope and evidence

- **Verified** means a firmware instruction, data byte, or offline CPU result supports the statement.
- **Inferred** means the stated behavior explains those observations but lacks a schematic or component datasheet match.
- **Unknown** means the examined evidence does not establish the fact.

PSoC denotes the Cypress microcontroller. FPGA denotes the programmable logic device.
EMIF is the PSoC external memory interface. SPI and I2C are serial control buses.
ADC means analog-to-digital converter. DAC means digital-to-analog converter.
DSP means digital signal processor. GPIO means general-purpose input/output.
UDB means PSoC universal digital block. RAM means volatile memory.

The primary source is `/tmp/apogee-fw/decompiled.c`, with machine code and tables from `/tmp/apogee-fw/flash.bin`.
Addresses without a prefix name PSoC CPU addresses. Function addresses identify entry points.
Flash file offsets equal CPU flash addresses minus `0x10000`.

**Verified:** `0x21970` copies flash `0x253D8..0x2619F` to RAM `0x1FFF8108..0x1FFF8ECF`.
The descriptor at `0x253C4` contains `0x253D8, 0x1FFF8108, 0xDC8, 0x1B28`.
Tables below cite both addresses where useful.

`NOTES-vendor-driver.md` sections 5.6, 5.8–5.13, and 8 supply host control names.
`probe-results.md` supplies prior device observations, not new tests.
This analysis used no hardware access.
Protocol dispatch and argument validation belong to the protocol report.
Initial pin configuration belongs to the startup report. Front-panel behavior belongs to the UI report.

## Explanation

### Bus topology and part identity

| Status | Target | Evidence and limits |
|---|---|---|
| Verified | FPGA EMIF base `0x60800000` | `0x12610` writes four bytes, least significant byte first. `0x12658` writes two bytes in the same order. |
| Verified | Eight SPI preamp addresses, 0–7 | `0x10074`, `0x105FC`, `0x108BC`. Each channel initially uses its channel number as its bus address. |
| Verified | I2C address `0x49`, branches 0 and 1 | `0x11164`, `0x11460`, `0x114A0`. FPGA `0x60800009` bit 3 selects the branch. |
| Inferred | Two eight-channel DAC-class devices at `0x49` | Each branch supplies eight output attenuation registers and a global mute bit. Evidence: `0x11218`, `0x1138C`, `0x113D4`. |
| Verified | I2C address `0x29`, branch 1 | `0x12690` sets the address and writes three bytes. `0x126D4` updates guitar gain. |
| Inferred | Dual guitar gain controller at `0x29` | The two guitar gain controls alter its first two bytes. Its exact analog topology is unknown. |
| Verified | I2C address `0x18`, paged registers | `0x12D28`, `0x12F44`. The branch selector is not set within these functions. |
| Inferred | Front-microphone ADC-class device at `0x18` | Hardware revision changes its initialization and gain path. Evidence: `0x10490`, `0x14A24`. |
| Verified | I2C addresses `0x70`, `0x71` | `0x128E8` initializes these targets. The pin map and front-panel outputs belong to the UI report. |
| Unknown | External audio chip manufacturer and part numbers | The examined routines expose no unambiguous part ID. Address `0x49` register `0x10` selects two code paths, not a named part. |
| Unknown | Rear ADC control target | No independent rear ADC serial initialization appears in `0x10490`. FPGA control bits can drive converter pins. |

**Verified:** the I2C API accepts seven-bit addresses.
`0x2278C` forms the address byte from the supplied address, with the write bit clear.
`0x11050` retries writes until status equals `2`.
Each attempt polls up to 200 times with `CyDelayUs(5)`.
The outer retry has no limit. `0x110F0` similarly retries reads until status equals `1`.

**Verified:** branch changes use a full shadow-register write, then `CyDelayUs(1)` at `0x11460`.
**Inferred:** FPGA bit 3 controls an I2C branch or target-enable selector.
**Unknown:** physical bus-switch implementation and branch accessibility of address `0x18`.

### Mute, power, and clock order

**Verified:** firmware delay helpers are `CyDelay` at `0x23AD4` and `CyDelayUs` at `0x23B18`.
Their initial multipliers are 33000 and 33 at RAM `0x1FFF8EC0` and `0x1FFF8EC4`.
Elapsed-time routines `0x20364` and `0x20378` use the complemented 16-bit TMR0 counter from `Counter_ReadCounter` at `0x232BC`.
On wrap, `0x20378` subtracts one additional tick.
**Unknown:** the timer route and tick duration. The sequences below preserve raw tick counts, distinct from fixed `CyDelay` waits.

| Status | Transition | Exact firmware order |
|---|---|---|
| Verified | Full analog mute, `0x15288` | Write `0xFF` to all 16 DAC attenuation registers. Set register `0x0A` bit 0 on both branches. |
| Verified | Sample-rate change, `0x1455C` | Full mute. Store rate. Write ADC delay at `0x60800037`. Delay 100 ms. Call `0x10490(rate,0)`. |
| Verified | Clock-source change, `0x1459C` | Full mute. Store source. Delay 100 ms. Write source to `0x6080000F`. |
| Verified | Rate/converter sequence, `0x10490` | Clear FPGA `0x09` bits 7,6 and `0x0A` bit 3. Write rate at `0x0E`. Delay 500 ms. |
| Verified | Rate/converter continuation, `0x10490` | Set `0x0A` bit 3, then `0x09` bit 6. Initialize `0x18`. Optionally pulse DAC reset. Initialize DAC branches 0,1. |
| Verified | DAC reset, `0x111EC` | Set FPGA `0x0A` bit 2. Delay 1000 us. Clear bit 2. Delay 25000 us. |
| Verified | Mute release, `0x144C0` | After 500 elapsed ticks, restore all output levels. Clear both DAC mute bits. Restore front-microphone gain. |
| Verified | Internal-clock release request | The rate/source command path calls `0x1453C`. It arms the delayed release. Evidence: `0x16228`, cases `0x29`, `0x2A`. |
| Verified | External-clock release request | `0x15F58` requires FPGA status bit 6 clear and measured rate within ±5%. It then calls `0x1453C`. |
| Verified | External lock loss | `0x15F58` calls `0x14F54`, which performs full mute and cancels the release timer. |

**Inferred:** DAC register `0x0A` bit 0 is global soft mute.
**Verified:** the code asserts it before clock changes and clears it after the delayed output restore.
**Verified:** DAC reinitialization writes register `0x0A` with bit 0 clear, but leaves every attenuation register at `0xFF`.
Thus the full clock sequence does not keep the global mute bit asserted throughout.
Evidence: `0x11218`.
**Unknown:** converter ramp duration, relay state, analog settle time, and pop amplitude.
A firmware delay does not prove electrical safety for different hardware or a different clock sequence.

**Verified:** startup uses the state machine at `0x10168`:

| State | Status | Actions |
|---|---|---|
| 0 | Verified | Call `0x100EC`, then UI initialization. `0x100EC` drives control masks and includes 6000 us, 5 us, and 2 us delays. |
| 1 | Verified | Set FPGA `0x09` bit 4. Initialize targets `0x70/0x71`. Save the elapsed counter. |
| 2 | Verified | Read versions until at least 100 elapsed ticks. |
| 3 | Verified | After 5 ticks, set UDB10 mask `0x08`. Clear FPGA `0x0A` bit 7. |
| 4 | Verified | After 5 ticks, set FPGA `0x0A` bit 5. Initialize guitar target `0x29`. Reset and initialize eight SPI preamps. |
| 5 | Verified | Call `0x10490(44100,1)`, which includes the DAC reset pulse. |
| 6 | Verified | Hardware-ready state. `0x10148` returns true only here. |

**Verified:** shutdown begins with `0x10414` and continues through states 7–10 of `0x10168`:

- Assert both DAC mute bits, then wait 500 ticks.
- Clear FPGA `0x09` bits 7,6 and `0x0A` bit 3. Clear UDB10 mask `0x04`.
- Wait 10 ticks, then clear FPGA `0x09` bit 4.
- Wait 10 ticks, then clear UDB10 masks `0x10,0x02` and UDB06 masks `0x01,0x02`.
- Set FPGA `0x0A` bit 7, clear UDB10 mask `0x08`, and restore FPGA control defaults.

**Verified:** `0x10414` can bypass the initial mute state during incomplete startup.
**Unknown:** whether each control bit switches a supply, reset, enable, or relay.
The state-machine order is evidence, not a complete analog power specification.

## Register and sequence reference

### FPGA audio register map

All entries below use byte accesses. Offset means the value added to `0x60800000`.

| Offset / CPU address | Status | Meaning | Evidence |
|---|---|---|---|
| `0x02 / 0x60800002` | Verified | Bit 6 clear means PLL lock. Bits 5:3 plus 1 give hardware revision. | `0x15F58`, `0x11B4C` |
| `0x07 / 0x60800007` | Verified | Bits 0–7 invert Analog 1–8 phase. | `0x145E0`, `0x11C98` |
| `0x08 / 0x60800008` | Verified | Bits 0–3 select instrument mode. Bits 4,5 select output reference. Bits 6,7 enable inserts. | `0x14810`, `0x14B48`, `0x16C2E` |
| `0x09 / 0x60800009` | Verified | Bits 0,1 enable guitar Thru. Bit 2 disables word-clock termination. Bit 3 selects the I2C branch. | `0x16D1E`, `0x16EF8`, `0x11460` |
| `0x09 / 0x60800009` | Inferred | Bit 4 enables an audio power domain. Bits 6,7 control clocks or converter reset. Physical nets unknown. | `0x10168`, `0x10490`, `0x12D28` |
| `0x0A / 0x6080000A` | Verified | Bit 2 pulse precedes DAC initialization. Bit 3 toggles around rate changes. | `0x111EC`, `0x10490` |
| `0x0A / 0x6080000A` | Inferred | Bit 4 enables the shared phantom supply. Bit 5 enables audio hardware. Bit 7 is an active-low startup control. | `0x14698`, `0x14810`, `0x10168` |
| `0x0B / 0x6080000B` | Verified | Bit n is clear for +4 dBu input mode, set for other modes. | `0x14810`, `0x1198C` |
| `0x0C / 0x6080000C` | Verified | Bits 0–7 select -10 dBV reference on Line 3–10. | `0x14B48`, `0x11A10` |
| `0x0D / 0x6080000D` | Verified | Bits 0–7 enable soft limit on Analog 1–8. | `0x1463C`, `0x11A94` |
| `0x0E / 0x6080000E` | Verified | Rate index: 0=44100, 1=48000, 2=88200, 3=96000, 4=176400, 5=192000. | `0x11860` |
| `0x0F / 0x6080000F` | Verified | Clock source byte. Host names: 0 internal, 1 word clock, 2 coax, 3 optical 1, 4 optical 2. | `0x118E4`, host notes §5.8 |
| `0x18..0x1B / 0x60800018..0x6080001B` | Verified | Four-byte external-clock period measurement. | `0x12150` |
| `0x28 / 0x60800028` | Verified | Optical 1 uses mask `0x05`, optical 2 uses `0x0A`. Format 1 sets both bits, other values clear both. | `0x11D24` |
| `0x37 / 0x60800037` | Verified | Extra ADC delay byte for current sample rate. Both 88200 and 96000 select delay byte 3. | `0x152F0`, `0x15364`, `0x153A4` |
| `0x8B..0x94 / 0x6080008B..0x60800094` | Verified | Fine trim for Line 1–10, value `trim % 5`. | `0x14D28` |
| `0x200+d / 0x60800200+d` | Verified | Route source for destination d, `0≤d≤255`. | `0x11C24`, `0x11C5C` |
| `0x300+d / 0x60800300+d` | Verified | Route control, normally `0x08`. Inactive speaker sets use `0x18`. | `0x13DFC` |
| `0x1000+0x100m+0x80s+2c` | Verified | Two-byte mixer coefficient. CPU base `0x60801000`. Side s=0 left, 1 right. | `0x11BE4`, `0x12658` |

**Verified:** `0x1190C` updates a RAM shadow before it writes FPGA offsets `0x08..0x0D`.
Their initial bytes at flash `0x253E0` are `00 00 84 00 00 00`.
The shadow occupies RAM `0x1FFF907C..0x1FFF9081`.
Direct FPGA writes can desynchronize this shadow.

**Verified:** `0x12150` computes an intermediate frequency from `819200000000 / period`, then divides by two with upward adjustment for odd quotients.
It rejects period zero and `0x00FFFFFF`.
It rounds rates below 100000 to multiples of 10, otherwise to multiples of 100.
For optical ADAT at rate codes 2 or 3, it doubles the result.
**Unknown:** physical measurement interval and exact meaning of period saturation.

**Verified:** format value 1 corresponds to S/PDIF in the host enum. Value 0 corresponds to ADAT/SMUX.
The PSoC writes no separate SMUX mode in `0x11D24`.
**Inferred:** FPGA rate and optical format jointly determine SMUX behavior.

### SPI preamp control

**Verified:** `0x108BC` transmits:

```text
word = (channel_address << 13) | 0x1000 | ((register & 7) << 9) | value
```

**Verified:** `0x22244` writes the 16-bit word to `CYREG_B0_UDB14_F0`, CPU address `0x4000644E`.
It polls bit 2 at `CYREG_B0_UDB15_ST`, `0x4000646F`.
The caller first polls mask `0x11` at the same status register. Neither loop has a timeout.
**Unknown:** external chip select polarity, wire bit order, and the part number.

| Register / field | Status | Function and evidence |
|---|---|---|
| Register 3 = `1` | Verified | First initialization write per channel, `0x10634`. |
| Register 2 = `0` | Verified | Second initialization write per channel, `0x10634`. |
| Register 1 = `0` | Verified | Third initialization write per channel, `0x10634`. |
| Register 1 | Verified | Gain code. `0x106B8` maps 1–7 to 8 and caps values above 63 at 63. Zero stays zero. |
| Register 2 bits 0,1 | Verified | Two gain-range controls from `0x10710`. Their electrical roles are unknown. |
| Register 2 bit 2 | Verified | High-pass-filter control, `0x107C4`, `0x1478C`. |
| Register 2 bit 3 | Verified | Per-channel phantom control, `0x10840`, `0x14698`. |
| RAM `0x1FFF9054+2n` | Verified | SPI address for channel n. Next byte caches register 2. `0x105FC`. |

**Verified:** `0x15038` chooses the following gain segments.
Each row contains inclusive requested gain bounds, initial register-1 code, and register-2 bits 0,1.

| Channels | Gain range | Initial code | Bit 0 | Bit 1 | Status / table |
|---|---:|---:|---:|---:|---|
| Analog 1–2 | 0–18 | 12 | 0 | 1 | Verified, RAM `0x1FFF82C0`, flash `0x25590` |
| Analog 1–2 | 19–60 | 13 | 1 | 1 | Verified, same table |
| Analog 1–2 | 61–75 | 45 | 1 | 0 | Verified, same table |
| Analog 3–8 | 0–6 | 8 | 0 | 0 | Verified, RAM `0x1FFF82B0`, flash `0x25580` |
| Analog 3–8 | 7–24 | 8 | 0 | 1 | Verified, same table |
| Analog 3–8 | 25–75 | 8 | 1 | 1 | Verified, same table |

**Verified:** register-1 code equals `requested_gain - lower_bound + initial_code`.
The firmware first writes register 2.
If the code stays equal but range bits change, it writes code zero before the requested code.
Evidence: `0x15038`.
**Unknown:** analog gain error, transient amplitude, and whether zero means minimum gain or a special state.

| Input mode | Status | Hardware action at `0x14810` |
|---|---|---|
| +4 dBu, value 0 | Verified | Clear FPGA `0x0B` channel bit. Set range bits to 1,1. Write gain code zero. Disable high-pass filter. |
| -10 dBV, value 1 | Verified | Set FPGA `0x0B` channel bit. Apply requested gain 12 through the channel-specific range table. Disable high-pass filter. |
| Mic, value 2 | Verified | Set FPGA `0x0B` channel bit. Apply saved microphone gain, high-pass filter, and phantom state. |
| Instrument, value 3 | Verified | Set FPGA `0x0B` channel bit. Set `0x08` bit for channels 0–3. Apply saved instrument gain and filter. |

**Verified:** `0x14698` stores phantom requests even outside Mic mode, but only Mic mode writes the per-channel control.
It updates the shared-supply mask at RAM `0x1FFF910E`.
On a direct phantom change, it writes the shared supply before the SPI bit if the aggregate state changes.
On an input-mode change, `0x14810` writes the SPI bit before the shared supply.
No explicit phantom settle or discharge delay appears in either function.
**Unknown:** whether the circuitry itself controls the phantom ramp and protects mode transitions.

### Guitar gain and output controls

**Verified:** `0x12690(0x29)` sends `00 40 86` on I2C branch 1.
`0x126D4` updates byte 0 to `0x40 | (gain & 0x3F)` for Guitar 1.
It updates byte 1 to `gain & 0x3F` for Guitar 2.
It retains the other byte and byte 2, then sends all three bytes.

**Verified:** `0x14AB0` accepts guitar gains 0–45 at logical inputs 10 and 11.
**Verified:** output attenuation uses the DAC target, not the guitar gain target.
`0x14EF8` doubles the requested attenuation and writes branch 1, register 0 or 1.
`0x16D1E` sets FPGA Thru bits when the output-mode value is zero.
**Unknown:** the `0x29` third-byte bit meanings and its relationship to analog unity gain.

### Output DAC initialization and volume map

**Verified:** each DAC descriptor occupies 12 bytes at RAM `0x1FFF9064+12d`.
Its fields include I2C address, variant flag, branch selector, and register-`0x0A` shadow.
`0x10074` creates descriptors `(0x49, branch 0)` and `(0x49, branch 1)`.

**Verified:** `0x11218` selects the branch, delays 1 us, and reads register `0x10`.
It then executes one of these sequences, in listed order:

| Read result | Status | Register writes |
|---|---|---|
| `0x10 == 0` | Verified | `19=01`, `0A=0E`, `0E=09` below 88200 Hz or `0E=08` otherwise, `0B=9E`. |
| `0x10 != 0` | Verified | `10=70`, `0B=1D`, `0A=06` below 176400 Hz or `0A=02` otherwise. |
| Both paths | Verified | Write registers `00..07=FF`, in ascending order. |

**Unknown:** model-specific meanings of registers `0x0B`, `0x0E`, `0x10`, and `0x19`.
The register read distinguishes behavior, not a proven silicon identity.

The output map comes from RAM `0x1FFF82D0`, flash `0x255A0`.
Each pair stores `(branch, first attenuation register)`.

| Physical pair | Branch | Registers | Status |
|---|---:|---|---|
| Line 1–2 | 0 | `04,05` | Verified, `0x14DF8` and table |
| Line 3–4 | 0 | `06,07` | Verified, same |
| Line 5–6 | 1 | `02,03` | Verified, same |
| Line 7–8 | 1 | `04,05` | Verified, same |
| Line 9–10 | 1 | `06,07` | Verified, same |
| Guitar 1–2 | 1 | `00,01` | Verified, `0x14EF8` |
| Headphone 1 | 0 | `00,01` | Verified, `0x14F8C` |
| Headphone 2 | 0 | `02,03` | Verified, `0x14F8C` |

**Verified:** `0x14DF8` computes `2*attenuation + 30*dim + coarse_trim`, or `255 + coarse_trim` for mute.
`0x1138C` converts every value above 127 to `0xFF`.
Thus attenuation 64 reaches mute even without a separate mute flag.
**Inferred:** one DAC step is 0.5 dB, consistent with host attenuation units and the multiplication by two.

**Verified:** `0x14D28` clamps trim at 120.
It sends `trim/5` to the DAC and `trim%5` to FPGA `0x6080008B+channel`.
**Inferred:** the FPGA remainder supplies 0.1 dB steps if the DAC step is 0.5 dB.
**Unknown:** FPGA fine-trim transfer function and exact analog reference voltage.

**Verified:** speaker mode controls the number of pairs that share speaker volume.
`0x14F8C` maps modes `0..6` to pair counts `0,1,2,3,3,4,5`.
Headphone monitor indices 0 and 1 always select physical pairs 6 and 7.
Speaker monitor index 2 selects the first pairs.
`0x14C80` restores trim-only levels on pairs that leave speaker control.

### Front-microphone converter initialization

**Verified:** `0x10490` selects the newer path when hardware revision exceeds 2.
`0x12D28` clears FPGA `0x09` bit 7, waits 1000 us, then sets it.
It sends `00=00`, `01=01` to address `0x18`, then waits 100 us.
Register zero acts as the page selector in all subsequent sequences.

| Variant | Status | Ordered writes after reset |
|---|---|---|
| Revision ≤2, page 0 | Verified | `12=82, 13=84, 14=40, 33=28, 34=04, 3D=02, 50=02` |
| Revision >2, page 0 | Verified | `12=82, 13=82, 1B=20, 57=80, 58=3C, 59=50, 5A=00, 5B=0C, 5C=03, 56=80, 3D=02` |
| Revision >2, page 1 | Verified | `00=01, 33=40, 34=FC, 3B=00`. Set RAM `0x1FFF8184=1`. |
| Both, page 4 | Verified | `00=04`, then four block writes from the variant-specific tables below. |
| Revision ≤2, page 0 | Verified | `00=00, 51=88, 53=14, 52=00` |
| Revision >2, page 0 | Verified | `00=00, 51=80, 52=08` |

All rows cite `0x12D28`.
The first byte of each block is the register address, followed by its data bytes.

| Variant | RAM source | Flash source | Bytes | Status |
|---|---|---|---:|---|
| Revision ≤2 | `0x1FFF8188` | `0x25458` | 31 | Verified |
| Revision ≤2 | `0x1FFF81A8` | `0x25478` | 21 | Verified |
| Revision ≤2 | `0x1FFF81C0` | `0x25490` | 31 | Verified |
| Revision ≤2 | `0x1FFF81E0` | `0x254B0` | 21 | Verified |
| Revision >2 | `0x1FFF81F8` | `0x254C8` | 31 | Verified |
| Revision >2 | `0x1FFF8218` | `0x254E8` | 21 | Verified |
| Revision >2 | `0x1FFF8230` | `0x25500` | 31 | Verified |
| Revision >2 | `0x1FFF8250` | `0x25520` | 21 | Verified |

**Verified:** the four block addresses are `0x0E,0x2C,0x4E,0x6C`.
The first and third blocks have identical payloads. The second and fourth also match.
The offline checker prints every byte.

**Inferred:** page 4 holds paired digital-filter coefficient banks.
The older payload repeats `7F FF 00 00 00 00 00 00 00 00`.
The newer payload contains signed nonzero coefficients.
**Unknown:** coefficient word format, filter response, and the exact converter model.

**Verified:** `0x14A24` doubles the host front-microphone gain before `0x12F44`.
For the older path, `0x12F44` caps the doubled value at 40 and writes page 0 register `0x53`.
For the newer path, it caps at 80.
With RAM `0x1FFF8184=1`, it writes page 0 register `0x58`.
Otherwise it writes page 1 register `0x3B`.
`0x12FD0` selects the first path through `56=80`. `0x13000` selects the second through `56=00`.
**Inferred:** the newer firmware normally adjusts an automatic-gain target, rather than only a direct preamp gain.
**Unknown:** the older-path saturation above host gain 20 and the electrical meaning of the newer mode bit.

### GPIO and UDB runtime effects

| CPU register | Status | Runtime effects | Evidence |
|---|---|---|---|
| `0x4000647A`, `CYREG_B0_UDB10_CTL` | Verified | Shadow at `0x1FFF810C`, initially `01`. Masked updates through `0x1152C`. | `0x114FC`, `0x22A6C` |
| Same, mask `01` | Verified | Low/high pulse, 10 us each, after FPGA-ready handshake. | `0x11754` |
| Same, mask `04` | Inferred | Preamp reset or enable. Low, 40 delay cycles, high, then 100 ms delay. | `0x10694` |
| Same, mask `08` | Inferred | Audio power control, asserted before converter initialization and cleared late in shutdown. | `0x10168` |
| Same, mask `10` | Inferred | Reset for the `0x70/0x71` devices. Low/high with 5 ms intervals. | `0x128E8` |
| Same, mask `02` | Verified | Pulsed during `0x100EC`, cleared during shutdown. Net purpose unknown. | `0x100EC`, `0x10168` |
| `0x40006476`, `CYREG_B0_UDB06_CTL` | Verified | Shadow at `0x1FFF810D`, initially `04`. Masks `01,02` set during startup and cleared during shutdown. | `0x11578`, `0x22D5C` |

**Verified:** `0x10514` also controls direct GPIO P3[3] through `0x22048` and `0x2200C`.
The on path passes drive-mode value `0x0C` and data 1. The off path passes drive-mode value 2 and data 0.
**Unknown:** its external load and relationship to audio power. The startup report owns its pin configuration.
**Unknown:** package pins and PCB net names for these UDB outputs.
A UDB control register is not a direct GPIO-port register.
Do not assign power-rail names from sequence position alone.

### Route matrix

**Verified:** `0x11C24(d,s)` writes source first, then control `8`.
`0x11C5C(d,s,c)` writes an explicit control byte.
The firmware does not commit a complete route transaction atomically.

| Destination | Status | Function | Evidence |
|---|---|---|---|
| `00..09` | Verified | Line outputs 1–10 | `0x13DFC`, table `0x2556C` |
| `0A..0B` | Verified | Guitar outputs | Same |
| `0C..0D`, `0E..0F` | Verified | Headphones 1 and 2 | Same |
| `10..1F` | Verified | Optical outputs | Same |
| `20+2k`, `21+2k` | Inferred | Stereo inputs to mono-sum bus k | `0x13DFC` uses source `20+k` afterward |
| `30..51` | Verified | Record channels 0–33 | `0x14058`, `0x14188` |
| `52..53` | Verified | Coaxial S/PDIF outputs | `0x2556C` |
| `60..7D` | Verified | Mixer feeds for 30 physical input channels | `0x13860`, `0x141D8` |
| `80..8F` | Inferred | Playback feeds to mixer channels 30–45 | `0x13860`, `0x139C8` |
| `90..A9` | Inferred | Front-panel meter taps | `0x14020`, `0x13D10`, `0x13DFC` |
| `B0..B7` | Unknown | Reset route uses sources `60..67` | `0x139C8` |
| `C0..CF` | Verified | DSP inputs 0–15 | `0x1414C` |
| `E0..FF` | Unknown | Startup route uses sources `90..AF` | `0x13860` |

Source codes from the input table at RAM `0x1FFF8290`, flash `0x25560`:

| Source | Status | Signal |
|---|---|---|
| `00..07` | Verified | Analog 1–8 |
| `08..09` | Verified | Front microphone |
| `0A..0B` | Verified | Guitar 1–2 |
| `10..1F` | Verified | Optical 1–16 |
| `54..55` | Verified | Coaxial S/PDIF |
| `30..53` | Verified | Host playback 1–36, host notes §5.9 and reset table `0x25550` |
| `60..67` | Verified | Four stereo mixer outputs, `0x139C8`, `0x14058` |
| `68..6F` | Verified | Four stereo DAW mixer outputs, `0x13DA4`, `0x13DFC` |
| `70..7F` | Verified | DSP outputs 0–15, `0x14188` |

**Verified:** output destination indices 0–16 map to the following first-channel destinations:

```text
00 02 04 06 08 0A 52 10 12 14 16 18 1A 1C 1E 0C 0E
```

The table is at RAM `0x1FFF829C`, flash `0x2556C`.
`0x13DFC` routes both channels and updates related meter taps.
Inactive speaker sets receive control `0x18`, not a different source.
Mono mode first routes both source channels to a sum bus, then duplicates its output.
**Unknown:** the sum scale and the electrical behavior of route-control bit 4.

**Verified:** record reset uses table `0x25538`. Output reset uses `0x25550`.
`0x14058` forces record pair 15 to Mixer 1 and pair 16 to Mixer 4.
`0x13DFC` substitutes DAW mixer sources for selected playback pairs.
With both multi-unit flags set, mixer sources `60..67` become optical sources `10..17` for analog, guitar, coax, and headphone destinations.

### Mixer coefficient calculation

**Verified:** mixer banks 0–3 occupy `0x60801000..0x608013FF`.
Banks 4–7 occupy `0x60801400..0x608017FF` and implement DAW mixers.
Address formula: `0x60801000 + 0x100*bank + 0x80*side + 2*channel`.

**Verified:** `0x18420` maps nonzero fader values to `value/10 - 60` dB.
Zero maps to -200 dB.
`0x179EC` adds channel fader, master fader, pan attenuation, and gate attenuation in dB.
The gate contributes -200 dB when mute, visibility, master mute, or solo rules exclude a channel.
For a post-fader secondary mixer, it also adds Mixer 1's channel fader.
Pre-fader secondary mixers omit Mixer 1's mute and solo constraints.
Evidence: `0x179EC`.

**Verified:** `0x18470` evaluates the pan table at RAM `0x1FFF82FC`, flash `0x255CC`.
For each half-open interval, attenuation is `base - slope*(pan-start)`.

| Pan interval | Base dB | Slope | Status |
|---|---:|---:|---|
| 0–3 | 0 | 0 | Verified |
| 4–23 | -0.1 | 0.025 | Verified |
| 24–51 | -0.6 | 0.05 | Verified |
| 52–63 | -2 | 0.08 | Verified |
| 64–75 | -3 | 0.1 | Verified |
| 76–103 | -4.1 | 0.2 | Verified |
| 104–115 | -10 | 0.5 | Verified |
| 116–121 | -16 | 1 | Verified |
| 122–127 | -22 | 2.5 | Verified |
| 128 | -200 | 0 | Verified |

**Verified:** mono left uses `pan`, and mono right uses `128-pan`.
Stereo channels use balance: even channels feed left only, odd channels feed right only.
`0x17F2C` attenuates left only above center. `0x17F5C` attenuates right only below center.
The opposite side receives -200 dB.

**Verified:** `0x18534` converts dB to a 16-bit coefficient:

```text
if db < -60: return 0
threshold = 6
shift = 0
while db < threshold:
    threshold -= 6
    shift += 1
index = min(int((db-threshold)*10), 60)
return table[index] >> shift
```

The 61-entry table occupies RAM `0x1FFF8374..0x1FFF83ED`, flash `0x25644..0x256BD`.
**Verified:** offline execution of the actual Thumb function produced:

| dB | Coefficient | Status |
|---:|---:|---|
| -200, -60.1 | `0000` | Verified |
| -60 | `0008` | Verified |
| -12 | `0800` | Verified |
| -6 | `1000` | Verified |
| -3 | `168C` | Verified |
| 0 | `2000` | Verified |
| +3 | `2D18` | Verified |
| +6 | `4000` | Verified |
| +12 | `8000` | Verified |

**Inferred:** the FPGA interprets `0x2000` as unity in an unsigned fixed-point gain representation.
The exact 6 dB shifts approximate factors of two rather than exact decimal logarithms.
**Unknown:** FPGA accumulator precision, saturation, and behavior at excessive total mix gain.

**Verified:** `0x18638` writes DAW input coefficients for channels 0–29.
Its mute polarity differs: command `0x93` value zero forces silence.
`0x187EC` sets a selected playback pair to unity, with no cross-channel coefficient, in slots 30–45.

### DSP core control

| CPU address | Status | Meaning | Evidence |
|---|---|---|---|
| `0x60801800` | Verified | Selected thread for code operations | `0x13574`, `0x133F4` |
| `0x60801802` | Verified | Eight halt-slot enable bits | `0x132DC`, `0x13388` |
| `0x60801805` | Verified | Coefficient begin handshake, write thread then poll bit 5 | `0x136FC` |
| `0x60801806` | Verified | Coefficient end handshake, write thread then poll bit 5 | `0x137C8` |
| `0x60801807..0x6080180C` | Verified | Six core-version bytes | `0x17404` |
| `0x6080180E` | Verified | Cycles per sample per thread | `0x136E4`, host notes §8.1 |
| `0x6080180F` | Verified | State-copy control, bit 0 busy, write 2 to start | `0x135E8` |
| `0x60801810` | Verified | State-copy thread | `0x135E8` |
| `0x60801811` | Verified | State-copy destination start | `0x135E8` |
| `0x60801812` | Verified | State-copy count written by PSoC | `0x135E8` |
| `0x60801820+i` | Verified | Halt-slot first address | `0x132DC` |
| `0x60801828+i` | Verified | Halt-slot inclusive last address | `0x132DC` |
| `0x60801830+i` | Verified | Halt-slot thread | `0x132DC` |
| `0x60801C00+4a` | Verified | Code word a | `0x13574` |
| `0x60802000+4a` | Verified | Coefficient word a | `0x13754` |
| `0x60802400+4j` | Verified | State transfer buffer word j | `0x135E8` |

**Verified:** code writes select a thread if it differs from RAM `0x1FFF9098`, then write four little-endian bytes per word.
The code index wraps as an eight-bit value in `0x13574`.
Coefficient writes do not explicitly write `0x60801800` in `0x13754`.
They use the begin/end handshake registers, each with up to 10000 polls and 1 us delays.
After timeout, the firmware continues without an error result.
**Unknown:** FPGA thread selection semantics when the handshake protocol is unavailable.

**Verified:** `0x132A4` enables the newer DSP protocol only when version byte `0x60801807` is nonzero.
State operations and coefficient handshakes depend on that flag.

**Verified:** a halt takes the first free slot, writes start, end=`start+count-1`, and thread, then writes the enable mask.
It waits 25 us. A ninth simultaneous halt is silently discarded.
Resume writes mask zero and waits 25 us, so every halt ends together.
Evidence: `0x132DC`, `0x13388`.

**Verified:** a first state chunk waits at most 1000 polls of 100 us, then proceeds even if busy persists.
It saves the start address and resets an eight-bit count.
Each chunk writes buffer index `chunk_start - first_start + word_index`.
The last chunk writes start, thread, count, then control `2`.
Evidence: `0x135E8`.

**Verified:** the state erase path at `0x13460` differs from the state-write path.
It writes zeros at `0x60802400 + 4*(start+j)`, not buffer index j.
It sends RAM `0x1FFF909A` as count, rather than the request count.
**Inferred:** partial state erase can use stale transfer state and overwrite unrelated words.
Prior hardware tests in `NOTES-vendor-driver.md` §8.7 also found that state copy ignores the count and replaces all 256 words.
That full-copy behavior is prior experimental evidence, not a property proven by PSoC code alone.

**Verified:** `0x1421C` configures DSP routes with three bytes: DSP input, DSP output, mode.
For physical input r, the writes occur in this order:

| Destination | Mode condition | Source | Status |
|---|---|---|---|
| `C0 + input` | Bit 0 set | Physical input source r | Verified, `0x1414C` |
| `60 + r` | Bit 0 set | `70 + output`, otherwise physical input r | Verified, `0x141D8` |
| `30 + r` | Bits 0 and 1 set | `70 + output`, otherwise physical input r | Verified, `0x14188` |

**Verified:** route arithmetic truncates to eight bits.
`0x140E8` returns source zero when r exceeds 29.
**Inferred:** out-of-range arguments can redirect unrelated routes and create feedback.
The protocol report owns the full validation analysis.

## Safety notes

| Status | Hazard | Evidence and constraint |
|---|---|---|
| Verified | Phantom transitions lack explicit discharge delays | `0x14698`, `0x14810`. Preserve the original order until the analog circuit is known. |
| Unknown | Phantom-safe connectors and load conditions | Firmware cannot establish microphone compatibility, hot-plug limits, or discharge time. |
| Verified | I2C or SPI failure can block control indefinitely | `0x11050`, `0x110F0`, `0x108BC`, `0x22244` have unbounded waits. A mute request can fail to complete. |
| Verified | Clock changes require mute and delayed restore | `0x1455C`, `0x1459C`, `0x144C0`. Do not replace this sequence with a rate-register write alone. |
| Verified | DAC initialization distinguishes two hardware variants | `0x11218`. Do not force one register sequence onto both variants. |
| Verified | Direct register writes can conflict with cached state | FPGA shadow at `0x1FFF907C`, DAC mute shadows in `0x1FFF9064` descriptors. |
| Inferred | DSP code or routes can produce full-scale output or feedback | `0x13574`, `0x1421C`. Keep all analog outputs muted during unverified DSP changes. |
| Verified | DSP handshakes can time out without cancellation | `0x136FC`, `0x137C8`, `0x135E8`. A completed command does not prove hardware acceptance. |
| Verified | State erase uses the transfer count cache | `0x13460`. Do not treat partial erase as an isolated memory operation. |
| Unknown | Supply, relay, and reset pin identities | `0x10168`, `0x1152C`, `0x11578`. A wrong polarity can disable protection or change power order. |
| Verified | These audio helpers contain no direct flash-program primitive | The mapped SPI, I2C, EMIF, gain, and converter routines above only write peripheral or RAM state. |
| Unknown | Durable side effects of arbitrary external-register writes | Part identities and device register specifications remain unresolved. Avoid undocumented register experiments. |

## Proposed tests

### Offline checks

Run the complete audio checker:

```sh
uv run --with unicorn python scripts/firmware/psoc-audio-check.py
```

**Verified:** this command passed relocation checks, ten coefficient cases, and three pan cases against the supplied flash image.
The checker maps only flash and RAM in an emulated CPU.
It requires each function to reach the return address before the instruction limit.
It rejects optimized Python runs because optimization removes its assertion checks.
Run its three execution-guard tests:

```sh
uv run --with unicorn python scripts/firmware/psoc-audio-test.py -v
```

Risk: no hardware access. The commands can install the Unicorn Python dependency.

### Physical evidence before active tests

**Unknown:** package markings, bus-switch topology, and power-net labels need a board inspection or schematic.
Proposed inspection: photograph the unpowered board and correlate audio chip markings with the address/register sequences above.
Risk: enclosure access can expose stored charge or damage connectors. Use the owner's approved service procedure.

No active hardware command is proposed.
A mute, phantom, clock, or DSP experiment requires an agreed load, electrical limits, and a recovery procedure first.
