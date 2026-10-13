# PSoC dispatcher, transport, and persistent state

## Scope and evidence

**Verified — static:** This map covers application firmware 1.5.3, identified by `0x17404`, from `/tmp/apogee-fw/flash.bin`.
The image spans CPU addresses `0x10000–0x3FFFF`. File offsets equal CPU addresses minus `0x10000`.
Its SHA-256 is `a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8`.

**Verified — method:** Ghidra output supplied function boundaries and control flow.
Thumb instructions supplied the malformed-input checks below. The shared Ghidra project was not modified.
`scripts/firmware/psoc-protocol-map.py` reproduces the tables and instruction views without device access.
Linear disassembly also decodes literal pools as instructions. Treat only established code ranges as code.

**Unknown — execution:** No firmware or device tests were performed for this report.
“Verified” means visible in static code or image bytes, unless a row explicitly cites prior device tests.
Hardware effects, display internals, and firmware-update internals belong to the audio, front-panel, and update reports.

Terms:

| Term | Definition |
|---|---|
| PSoC | Cypress microcontroller that executes this application |
| FPGA | Field-programmable gate array that exposes the mailbox and hardware controls |
| EMIF | External Memory Interface, the PSoC byte bus at `0x60800000` |
| EEPROM | Electrically erasable persistent memory at `0x40008000` |
| RX / TX | Host-relative directions: RX reaches the host, TX reaches the PSoC |
| Record | One command inside a mailbox message |
| `p1`, `p2`, `d` | First parameter, second parameter, and data bytes of an internal command |
| Source | Dispatcher origin: 0 local, 1 host, 2 EEPROM replay |
| CRC | Cyclic redundancy check, an eight-bit integrity value, not authentication |

## Execution and event map

### Application loop

**Verified:** `0x1F8FC` is the application entry and endless cooperative loop, not `0x15F58`.
`0x15F58` is a periodic state callback registered with period 500 by `0x16168`.
The timer unit remains **Unknown** here. `0x20280` uses a complemented 16-bit hardware counter from `0x232BC`.

| Phase | Exact call order or action | Evidence |
|---|---|---|
| Initialization | Enable interrupts, peripherals, timer table, settings defaults, power state, FPGA readiness | Verified: `0x1F90A–0x1F91E` |
| Subsystem initialization | DSP state, FPGA `0x2D=1`, audio state, routes, protocol state, UI, mixers, updates, interrupts | Verified: `0x1F922–0x1F950` |
| Start services | Register periodic state callback, enable FPGA events, initialize matrix | Verified: `0x1F954–0x1F95C` |
| Not ready | Call hardware state machine `0x10168` until `0x10148` returns true | Verified: `0x1F960–0x1F96A`, ready state `0x1FFF8EEC=6` |
| First ready pass | Reset output and input routes with source 2 | Verified: `0x1F970–0x1F984` |
| Each ready pass | Audio service `0x144C0`, EEPROM service `0x20498`, UI service `0x19390` | Verified: `0x1F986–0x1F98E` |
| Every pass | Panel events `0x1FA94`, FPGA events / receive `0x1FF6C`, reports `0x15668`, timers `0x20280` | Verified: `0x1F9A2–0x1F9B2` |

**Verified:** The timer table holds ten 16-byte entries at `0x1FFFA0A8`.
Each entry holds callback, argument, 16-bit period, 16-bit elapsed count, and enabled flag (`0x2014C`, `0x2019C`, `0x20280`).
A callback runs at most once per scheduler pass. Its elapsed count then becomes zero (`0x20280`).

| State at `0x1FFF8F0C` | Periodic callback behavior | Evidence |
|---|---|---|
| 0 | Wait for hardware ready and audio-ready predicate `0x144A8`, then select 1 | Verified: `0x15F80–0x15F9C` |
| 1 | Validate EEPROM, replay records with source 2, optionally report power-on, then select 3 | Verified: `0x15F9E–0x15FFA` |
| 2 | Initialize defaults, save synchronously, reload version reports, then select 1 | Verified: `0x15FFC–0x1600E` |
| 3 | Sample external lock and DSP cycle count | Verified: `0x16010–0x16152` |
| 4 | No callback action. Suspend helper selects 4, resume helper changes 4 to 0 | Verified: `0x1618C`, `0x161A4`, dispatch limit at `0x15F64` |

**Verified:** Factory reset command `0x51`, value `0xAB`, calls `0x17004` and selects state 2.
It does not reset defaults immediately inside the parser (`0x16F1A`, `0x17004`).

### FPGA event handshake

**Verified:** PSoC FPGA byte address `a` maps to CPU address `0x60800000+a`.
The following event bits are distinct from the host `PSOC_EVENT` bits.

| PSoC address | Role | Evidence |
|---|---|---|
| `0x6080001C + bit/8` | Read event status | Verified: `0x116F8` |
| `0x60800020 + bit/8` | Read-modify-write event enable | Verified: `0x1167C` |
| `0x60800024 + bit/8` | Write one event-clear bit | Verified: `0x11614` |
| `0x60800002`, bit 0 | Link-state input to host state machine | Verified: `0x1FD84`, `0x1FEE8` |
| `0x60800003` | Write `0xA2` after report sends | Verified: `0x11D98`, caller `0x15668` |

| Event bit | ISR action and deferred action | Evidence |
|---|---|---|
| 0 | Latch bit, clear hardware flag, increment software counter | Verified: `0x1FD84`, `0x1FF6C` |
| 1 | Latch bit and clear hardware flag. Deferred receive loop consumes up to eight slots | Verified: `0x1FD84`, `0x1FF6C` |
| 2 | Clear report iterators and masks. If status bit 0 is set, record host-reset acknowledgement | Verified: `0x1FF6C`, `0x21314`, `0x153EC` |
| 3 | Inspect status bit 0. Clear host state on disconnect or select state 1 on connect | Verified: `0x1FD84` |
| 4 | No ISR branch found | Unknown: branch set in `0x1FD84` excludes 4 |
| 5 | Latch bit, clear hardware flag, increment counter at `0x1FFF8FB8` | Verified: `0x1FD84`, `0x1FF6C` |

**Verified:** `0x20100` enables bits 1, 2, 3, and 5.
The ISR at `0x1FD84` records flags in `0x1FFF8FBC` and sets `0x1FFF8FA8`.
`0x1FF6C` disables the FPGA interrupt component around deferred work, then enables it again.

**Verified:** Host state `0x1FFF8FC4` uses 0 disconnected, 1 initial connection, and 2 protocol-ready (`0x1FD84`, `0x1FEE8`, `0x1FEC8`).
State 1 requires status bit 0, ten counter increments, and acknowledgement flag `0x1FFF8FC8` before state 2.
The counter increments once per call, not once per measured time interval (`0x1FEE8`).
RX reports require state 2. TX records wait for state 2 (`0x15668`, `0x1FF6C`).

**Verified — host evidence:** `NOTES-vendor-driver.md` §5.5 maps BAR0 `0x7E0` bit 1 to host write `0xABCD1234` at `0xBE0`.
Bit 0 causes host slot reset, restart notification, and DMA register refresh.
The host clears `0x7E0` after a nonzero event.

**Inferred:** FPGA logic mediates these host events and the PSoC event bits.
No direct application access to `0x608007E0`, `0x60800BE0`, or `0xABCD1234` was found in the mapped protocol code.
**Unknown:** The exact FPGA logic that generates restart events and validates the magic word.
Do not equate host event bit 1 with PSoC event bit 1.

## Mailbox and record format

### Shared slots

| PSoC CPU address | Object | Evidence |
|---|---|---|
| `0x60800400 + 0x78*n` | RX slot data, eight slots, 120 bytes each | Verified: `0x11ED0–0x11F12` |
| `0x608007C0 + 4*n` | RX slot state | Verified: `0x11F14–0x11F20` |
| `0x60800800 + 0x78*n` | TX slot data | Verified: `0x1203C–0x120C6` |
| `0x60800BC0 + 4*n` | TX slot state | Verified: `0x11FE0–0x12034` |
| `0x60800BE4` | RX write index | Verified: `0x11E4C`, `0x11F24` |
| `0x60800BE8` | RX read index | Verified: `0x11E88–0x11EAE` |
| `0x60800BEC` | TX write index | Verified: `0x11F76–0x11F9C` |
| `0x60800BF0` | TX read index | Verified: `0x11F9E–0x11FC4`, `0x120E2` |

**Verified:** Multi-byte mailbox reads use separate byte loads, low byte first (`0x11F76–0x11FC4`).
`0x12610` writes a 32-bit value as four byte stores, low byte first.
No atomic snapshot or retry protects the four-byte index reads.

**Verified:** RX space exists when `(write+1)&7 != read` (`0x11DB0`).
The sender retries a full ring ten times with delay argument 1 (`0x11EC2–0x11ECC`, `0x11F32`).
It copies data, writes state `word_count|0x20`, then advances the write index (`0x11EEE–0x11F2A`).
Normal report batches use at most 29 words (`0x15668`).
The low-level sender itself has no word-count, pointer, or index bounds check (`0x11E4C`).

**Verified:** TX receive requires unequal indices and nonnull destination/count pointers (`0x11FC6–0x11FDC`).
It accepts any nonzero slot state, not specifically bit 5 (`0x12036–0x1203A`).
It copies `state&31` words without a 30-word clamp, clears state, then advances the read index (`0x1204C–0x120E8`).
A zero state stalls that slot. A nonzero state with zero length consumes the slot but ends the current drain pass.

**Verified:** The receive buffer starts at `0x1FFFA030`, with the next object at `0x1FFFA0A8` (`0x1FF6C`, `0x2014C`).
A 31-word receive writes its final word over the first timer callback at `0x1FFFA0A8`.
Instructions `0x1204E` and `0x120B8` establish the unchecked count and store.
The source word comes from the next slot, or slot-state space for index 7.

### Wire records and internal commands

**Verified:** Every mailbox message begins with two header words, followed by records (`0x153F8`).
The parser reads the header into a local 64-bit variable, but does not authenticate it or copy it into the internal command.
Normal reports use two zero header words (`0x15668`, `0x15C50`).

| Type | Wire bytes after the header | Parser behavior | Evidence |
|---|---|---|---|
| 1 | `01 cmd p1 value` | Set `p2=0`, copy one data byte, dispatch source 1 | Verified: `0x15480–0x154D8` |
| 2 | `02 cmd p1 p2 len data... padding` | Copy up to 99 declared bytes, dispatch source 1 | Verified: `0x154DA–0x155D2` |
| 3 | `03 cmd p1 p2` | Mark command/p1 report. Ignore p2 | Verified: `0x1561C–0x1563E`, `0x208E0` |
| 4 | `04 00 00 00` | Set Get-all request flag `0x1FFF9140` | Verified: `0x155D4–0x1561A` |
| Other | Any other first byte | Stop this message without error report | Verified: `0x15460–0x15464`, `0x15640` |

| Internal offset | Field | Evidence |
|---|---|---|
| `0x00–0x07` | Reserved/header area, uninitialized by host parser | Verified: stack object starts at `r7+8`, stores start at `r7+0x10`, `0x15496` |
| `0x08` | Command ID | Verified: `0x1624A` |
| `0x09` | p1 | Verified: parser `0x154A4` |
| `0x0A` | p2 | Verified: parser `0x154B6`, `0x15520` |
| `0x0B...` | Data, without any stored length or type | Verified: `0x154B2`, `0x1555E` |

**Verified:** Types 1 and 2 reach the same dispatcher. The dispatcher cannot check the original type or declared length.
A short record can invoke a handler that consumes more bytes than the parser initialized (`0x16228`, `0x20918`).

### Instruction-confirmed malformed input

| Input | Actual result | Evidence |
|---|---|---|
| Message length 0–2 words | No record parse | Verified: `cmp #2`, `bls`, `0x1541C–0x1541E` |
| Type 2 with fewer than two words left | Stop without dispatch | Verified: `0x154DA–0x154EC` |
| Type 2 length 0 | Dispatch with unchanged local data bytes. Advance two words | Verified: copy loop `0x15562–0x1556C`, call `0x155CE` |
| Type 2 length 1–3 | Advance **three** words, not two. The next packed record loses its first word | Verified: `0x1556E–0x155A2` |
| Type 2 length 4–99 | Copy declared length without comparison against remaining message bytes | Verified: `0x15538–0x1556C` |
| Type 2 length 100–255 | Copy no data, set stop flag, **still dispatch** with current command and stale data | Verified: `0x1553C–0x1553E`, `0x155C0–0x155CE` |
| Type 1 before multi-byte handler | Only data byte 0 becomes valid. Later bytes retain stack contents or prior record data | Verified: `0x154B2`, no buffer clear in `0x153F8` |
| Type 3 or valid type 4 before another record | Word counter advances, record pointer does not. The same request repeats until the counter reaches message length | Verified: `0x15608–0x15612`, `0x15634–0x1563E` |
| Type 4 with any nonzero parameter | Stop without Get-all | Verified: `0x155DC–0x155F6`, `0x15614` |
| Index outside 0–7 | Raw index participates in slot address arithmetic. Only next index gets mask 7 | Verified: `0x11ED0`, `0x11FE0`, `0x1203C`, `0x120DA` |

**Inferred:** A type-2 overread can expose adjacent SRAM as command data or trigger unintended hardware operations.
The parser source starts in `0x1FFFA030`, so the unchecked copy can cross the timer table (`0x15556`, `0x2014C`).
Exact consequences depend on command, indices, and RAM state. No exploit or malformed-device test was performed.

## Complete command map

### Dispatch contract

**Verified:** The dispatcher uses 215 Thumb targets at `0x1625C–0x165B7`, indexed by `cmd-1` (`0x1624A–0x16256`).
Commands outside `0x01–0xD7`, and unused table entries, reach default `0x16F74`.
The dispatcher returns zero regardless of accepted commands (`0x16234–0x16236`, `0x16F9A`).
It emits no generic success or failure response.

**Verified:** Unless a case manages state itself, source 0 or 1 calls settings write `0x20918` after the handler (`0x16F76–0x16F8A`).
Source 1 and 2 then call UI hook `0x19738` (`0x16F8E–0x16F96`).
Source 0 does not call that hook.
The hook also forwards every command to active UI objects when `0x1FFF95BC=0` (`0x19738`, `0x1DB7C`).
Those object-specific effects remain outside this report.
A state-table bounds rejection therefore does not prevent a preceding hardware handler.

**Verified:** The command table below states bytes consumed, not an enforced packet length.
All rows accept type 1 or 2 at the parser.
The settings table supplies valid stored dimensions. It does not validate all downstream hardware paths.
Command names follow the vendor host names in `NOTES-vendor-driver.md` §5.6–5.7.
Bare handler addresses and IDs in tables are hexadecimal.

| ID | Name | Case target → handler or action | Data bytes and dispatcher constraints |
|---|---|---|---|
| `01` | AnalogInputType | `16B7C → 14810` | 1. On non-replay change, clear this channel's group first |
| `02` | MicGain | `16B18 → 17368` | 1. Handler stores state. Channels 0–8 |
| `03` | InstrumentGain | `16B36 → 172EC` | 1. Handler stores state. Channels 0–3, 10–11 |
| `04` | SoftLimit | `16BC8 → 1463C` | 1 |
| `05` | PhantomPower | `16B54 → 14698` | 1 |
| `06` | PhaseInverse | `16BDC → 145E0` | 1. Dispatcher requires p1<8, normalizes nonzero |
| `07` | GroupID | `16C04 → 161DC` | 1. Also stores partner p1 XOR 1, except source 2 |
| `08` | HighPassFilter | `16B68 → 1478C` | 1 |
| `09` | InputRouting | `16C1C → 14058` | 1. No source-code check in dispatcher |
| `0A` | InsertEnable | `16C2E → 1190C` | 1. Requires p1<2, normalizes nonzero |
| `0D` | AnalogOutputReferenceLevel | `16C70 → 14B48` | 1 |
| `0E` | AnalogOutputTrim | `16C84 → 14D28` | 1 |
| `0F` | MainOutputMode | `16C98 → 13B90,14C80` | 1. No mode check |
| `10` | ActiveSpeakerSet | `16CAE → 13BDC` | 1. No mask check |
| `11` | OutputAttenuation | `16B06 → 14B98` | 1. Handler clamps value to 64, but not p1 |
| `12` | OutputMute | `16CBA → 14BD8` | 1. No p1 check before output state access |
| `13` | OutputDim | `16CCC → 14C2C` | 1. No p1 check before output state access |
| `14` | OutputSumToMono | `16CDE → 13C48` | 1 |
| `15` | OutputRouting | `16CF0 → 13DFC` | 1. No source-code check in dispatcher |
| `16` | FrontGuitarOutputMode | `16D1E → 1190C` | 1. p1=0 selects first output, all others select second. Value zero selects Thru |
| `19` | TalkbackMicOn | Default, state then UI hook | 1 |
| `1A` | OpticalPortFormat | `16DD4 → 11D24` | 1. Only value 1 selects the alternate format |
| `1C` | FrontGuitarOutputAttenuation | `16D52 → 14EF8` | 1. Apply only when stored `1D` is zero |
| `1D` | FrontGuitarMatchUnityGainMode | `16D82 → 14EF8` | 1. Select stored attenuation or input gain |
| `1E,1F` | ChannelPairAllocation | Default, no state entry | No dispatcher operation |
| `20` | KeyboardVolumeControl | Default, state | 1 |
| `21` | MeterPeakHold | Default, state then UI hook | 1 |
| `22` | MeterOverHold | Default, state then UI hook | 1 |
| `23` | ActiveEncoderSelect | Default, state then UI hook | 1. Does not trigger a save by itself |
| `24` | LockHomeScreen | Default, state | 1 |
| `25` | TouchPadAssignment | Default, state then UI hook | 1 |
| `26` | PeripheralPrefix | Default, state | 1 |
| `27` | Identify | `16EB6 → timer 10544` | 1. Zero cancels timer, nonzero allocates a period-30 timer |
| `28` | ClearMeters | Default, state then UI hook | 1 |
| `29` | SampleRate | `16DF6 → 21670,1455C` | 1. Indices 0–5 map rates. Every other byte maps 44.1 kHz |
| `2A` | ClockSource | `16E46 → 1459C` | 1. Zero marks internal lock true, others clear lock state |
| `2B` | WordClockInputTermination | `16EF8 → 1190C` | 1. Zero/nonzero test |
| `2C` | ResetRouting | `16D02 → 139C8/13AE0` | 1. Zero resets outputs, nonzero resets inputs |
| `2D` | ExtraADCDelay | `16696 → 20918,153A4` | 6 stored bytes, no received-length check |
| `32` | MixerChannelFaderLevel | `169AA → 17854` | 2, big-endian. Store and copy stereo partner before hardware call |
| `33` | MixerChannelPan | `16768 → 179EC` | 1. Store and stereo-partner propagation |
| `34` | MixerChannelSolo | `16A50 → 17930` | 1. State has no p2 dimension |
| `35` | MixerChannelMute | `16768 → 177E8` | 1. Store and stereo-partner propagation |
| `38` | MixerChannelIsVisible | `167BC → 179EC/17930/178E4` | 1. State has no p2 dimension. Zero also clears solo and solo-safe |
| `39` | MixerChannelIsStereo | `168AA → 15E18,179EC` | 1. A changed even channel updates partner and all four pans |
| `3A` | MixerChannelSoloSafe | `16A82 → 178E4` | 1. State has no p2 dimension |
| `40` | Versions | Default, state | 3, p1 0–3. Host set can overwrite report state |
| `41` | UnitID | Default, no state | Report-only implementation in `15C50` |
| `42` | ExternalClockLock | Default, state | 1. Host set can overwrite report state |
| `43` | PowerSwitchOn | Default, state | 1. UI hook has no case for this ID |
| `44` | GetAllComplete | Default, no state | Report-only implementation in `15668` |
| `50` | FunctionalTestMode | Default, UI hook | 1 consumed by `19738`. No state entry |
| `51` | FunctionalTestResetAll | `16F1A → 17004`, UI hook | 1. Value must equal `AB` for default reset |
| `52,53` | FunctionalTestResults | Default, state | 2 / 3 |
| `60` | FirmwareUpdateDFUMode | `16F2A → 17FB4`, UI hook | 1. Handler recognizes 0,1,2. Other values select error state |
| `61` | FirmwareUpdateComplete | `16F3C → 18198` | Ignores command data. Handler emits two-byte status/CRC report |
| `62` | FirmwareUpdatePacket | `16F48 → 18098` | Handler consumes **p1 bytes**, not wire len |
| `63` | RestartPSocFirmware | `16F62 → 18344`, UI hook | 1. Handler branches on 0 or 1 |
| `64` | PLLClockLock | Default, state then UI hook | 1 |
| `66` | MultiUnitSettings | `16722 → 20918,17998` | 2 stored bytes. First byte zero also clears solo channel 46 |
| `90` | MixerIsPreFader | `16AB4 → 179BC` | 1. Ignore p1=0 and source 2 |
| `91` | DAWMixerFaderLevel | `166EC → 18638` | 2 stored bytes |
| `92` | DAWMixerPan | `166EC → 18638` | 1 |
| `93` | DAWMixerMute | `166EC → 18638` | 1 |
| `94` | DAWMixerRouting | `166AE → 140C0,187EC` | 1. Hardware gets `80` when byte is zero, state retains zero |
| `A0` | OpticalIsSubMix | Default, state | 1 |
| `D0` | DSPCoreWriteCode | `16614 → 13574` | Four-byte prefix plus `4*p1` data bytes. p2=start address |
| `D1` | DSPCoreWriteCoefficients | `16636 → 13754` | Four-byte prefix plus `4*p1` bytes. No count/length correlation |
| `D2` | DSPCoreVersion | Default, state | 7 |
| `D3` | DSPCoreRouting | `1667A → 1421C` | 3, input channel, output channel, mode. p1=record input index |
| `D4` | DSPCoreWriteStateInit | `16658 → 135E8` | Four-byte prefix plus `4*p1` bytes |
| `D5` | DSPCycleCount | Default, state | 1 |
| `D6` | DSPCoreErase | `165F4 → 133A8` | Four-byte prefix. p1=memory selector, p2=start address |
| `D7` | DSPCoreHaltResume | `165B8 → 132DC/13388` | p1=0 consumes data[2]=thread, data[3]=count. Any nonzero p1 resumes all |

**Verified:** Prefix bytes for `D0/D1/D4` are first-chunk flag, last-chunk flag, thread, and total count (`0x13574`, `0x135E8`, `0x13754`).
A parser-safe chunk can carry at most 23 words: `4+4*23=96`, below the parser limit 100.
The dispatcher does not enforce that limit on p1 (`0x16614–0x16678`).
The update handler likewise trusts p1 independently of wire length (`0x16F48`, `0x18098`).

**Verified:** All remaining byte IDs follow default and have no settings entry:
`00`, `0B–0C`, `17–18`, `1B`, `2E–31`, `36–37`, `3B–3F`, `45–4F`, `54–5F`, `65`, `67–8F`, `95–9F`, `A1–CF`, `D8–FF`.
The UI hook has no explicit switch branch for these IDs (`0x19738`).
Its generic active-object callback still receives them under the condition above.

### Values and checks at the boundary

**Verified:** Stored single-byte values generally accept the full range 0–255 (`0x20918`, `0x20820`).
Names such as “bool” describe host intent, not a settings-store constraint.
Hardware normalization does not necessarily normalize saved state.

| Command | Boundary behavior | Evidence |
|---|---|---|
| `02` | Hardware accepts 0–75 for p1 0–7, 0–40 for p1 8. Direct state path can retain rejected bytes | Verified: `0x14A32–0x14A84`, `0x17368` |
| `03` | Hardware accepts 0–65 for analog inputs, 0–45 for p1 10–11. Direct state path can retain rejected bytes | Verified: `0x14AC4`, `0x14B12`, `0x172EC` |
| `02,03` | Group logic limits the common relative gain change, rather than each request byte in isolation | Verified: `0x17020` |
| `09,15` | Route handlers reject p1>16. Input pairs 15/16 force source `60/66`, regardless of stored byte | Verified: `0x14068–0x14080`, `0x13E0C–0x13E10` |
| `07` | Partner update uses byte arithmetic. Table lookup rejects partner outside 0–11 | Verified: `0x161DC`, `0x21790` |
| `0E` | Hardware clamps trim to 120, generic state write stores the incoming byte | Verified: `0x14D28`, `0x16C84`, `0x16F8A` |
| `11` | Store at `0x1FFF9112+3*p1`, then hardware call. Clamp applies only to value | Verified: `0x14BA6`, `0x14BC2` |
| `12` | Read/write at `0x1FFF9111+3*p1`, no p1 bound | Verified: `0x14C00`, `0x14C18` |
| `13` | Read/write at `0x1FFF9110+3*p1`, no p1 bound | Verified: `0x14C54`, `0x14C6C` |
| `1C` | Failed settings read leaves local mode uninitialized before its zero test | Verified: `0x16D52`, read helper `0x209E0` |
| `29` | Invalid index selects 44100 Hz but generic state still records the invalid index | Verified: `0x21670`, `0x16DF6`, `0x16F8A` |
| `32–3A`, `90–94` | Settings bounds do not constitute dispatcher bounds. Hardware calls can follow rejected state accesses | Verified: branch targets above, `0x21790` |

**Inferred:** Output indices above 2 can corrupt protocol state before the settings store rejects them.
For example, command `11`, p1=14, targets `0x1FFF913C`, the receive command counter (`0x14BC2`, `0x154C4`).
The maximum p1=255 targets `0x1FFF940F`.
Mute and dim can alter adjacent bytes under the same unchecked arithmetic.

## Settings schema and reports

### Descriptor and RAM layout

**Verified:** There are 60 eight-byte descriptors at RAM `0x1FFF8BEC`, initialized from flash `0x25EBC`.
`0x203B4` assigns offsets and initializes defaults. `0x21738` searches descriptors by command ID.

| Descriptor offset | Width | Meaning | Evidence |
|---|---|---|---|
| 0 | 1 | Command ID | Verified: `0x21738` |
| 1 | 1 | Value width in bytes | Verified: `0x216E4`, `0x20918` |
| 2 | 1 | p1 count, zero means scalar | Verified: `0x216E4`, `0x21790` |
| 3 | 1 | p2 count, zero means no p2 dimension | Verified: `0x21790` |
| 4 | 2 | Little-endian byte offset in state pool, assigned at initialization | Verified: `0x203B4` |
| 6 | 1 | Simple default value | Verified: `0x205CC` |
| 7 | 1 | Volatile flag, bit 0 excludes persistence and Get-all | Verified: `0x20F5C`, `0x213C4` |

**Verified:** State pool base is `0x1FFFA148`.
The descriptors consume `0x66C` bytes. The allocator limit is `0x672` (`0x203B4`, `0x21790`, table bytes).
The last used byte is `0x1FFFA7B3`.

**Verified:** The stored address is `base+offset+width*p1+width*p1_count*p2` when both dimensions exist (`0x21790`).
A nonzero count accepts indices from zero through count minus one (`0x217C6`, `0x217EA`).
A zero p1 count ignores both incoming indices. A zero p2 count ignores incoming p2.
The helper checks only the starting address against the pool limit (`0x2181E–0x2182E`).
Compiled descriptors are internally consistent. EEPROM descriptors bypass their widths during replay.

**Verified:** In the following table, counts are raw descriptor bytes. Zero dimensions still occupy one value.
`R` denotes runtime-only. Hexadecimal EEPROM ranges are inclusive offsets from `0x40008000`.
Each row cites its flash descriptor address. RAM offsets follow `0x203B4` allocation order.

| ID | Width | p1 count | p2 count | RAM offset | Default byte | EEPROM range | Descriptor |
|---|---:|---:|---:|---|---|---|---|
| 01 | 1 | 12 | 0 | 000 | 02* | 0AC–0B7 | 25EBC |
| 03 | 1 | 12 | 0 | 00C | 00 | 0B8–0C3 | 25EC4 |
| 02 | 1 | 9 | 0 | 018 | 00* | 0C4–0CC | 25ECC |
| 07 | 1 | 12 | 0 | 021 | 00 | 0CD–0D8 | 25ED4 |
| 04 | 1 | 8 | 0 | 02D | 00 | 0D9–0E0 | 25EDC |
| 05 | 1 | 8 | 0 | 035 | 00 | 0E1–0E8 | 25EE4 |
| 06 | 1 | 8 | 0 | 03D | 00 | 0E9–0F0 | 25EEC |
| 08 | 1 | 8 | 0 | 045 | 00 | 0F1–0F8 | 25EF4 |
| 0A | 1 | 2 | 0 | 04D | 00 | 0F9–0FA | 25EFC |
| 09 | 1 | 17 | 0 | 04F | 00* | 0FB–10B | 25F04 |
| 1C | 1 | 2 | 0 | 060 | 00 | 10C–10D | 25F0C |
| 1D | 1 | 2 | 0 | 062 | 00 | 10E–10F | 25F14 |
| 0F | 1 | 0 | 0 | 064 | 01 | 110 | 25F1C |
| 0D | 1 | 10 | 0 | 065 | 00 | 111–11A | 25F24 |
| 0E | 1 | 10 | 0 | 06F | 00 | 11B–124 | 25F2C |
| 11 | 1 | 3 | 0 | 079 | 14 | 125–127 | 25F34 |
| 12 | 1 | 3 | 0 | 07C | 00 | 128–12A | 25F3C |
| 13 | 1 | 3 | 0 | 07F | 00 | 12B–12D | 25F44 |
| 14 | 1 | 3 | 0 | 082 | 00 | 12E–130 | 25F4C |
| 1A | 1 | 2 | 0 | 085 | 00 | 131–132 | 25F54 |
| 10 | 1 | 0 | 0 | 087 | 01 | 133 | 25F5C |
| 16 | 1 | 2 | 0 | 088 | 01 | 134–135 | 25F64 |
| 15 | 1 | 17 | 0 | 08A | 00* | 136–146 | 25F6C |
| 19 | 1 | 0 | 0 | 09B | 00 | R | 25F74 |
| 28 | 1 | 0 | 0 | 09C | 00 | R | 25F7C |
| 42 | 1 | 0 | 0 | 09D | 00 | R | 25F84 |
| 43 | 1 | 0 | 0 | 09E | 01 | R | 25F8C |
| 52 | 2 | 0 | 0 | 09F | 00 | R | 25F94 |
| 53 | 3 | 0 | 0 | 0A1 | 00 | R | 25F9C |
| 61 | 2 | 0 | 0 | 0A4 | 00 | R | 25FA4 |
| 40 | 3 | 4 | 0 | 0A6 | 00 | R | 25FAC |
| 20 | 1 | 0 | 0 | 0B2 | 02 | 147 | 25FB4 |
| 21 | 1 | 0 | 0 | 0B3 | 01 | 148 | 25FBC |
| 22 | 1 | 0 | 0 | 0B4 | 02 | 149 | 25FC4 |
| 23 | 1 | 0 | 0 | 0B5 | 00 | 14A | 25FCC |
| 24 | 1 | 0 | 0 | 0B6 | 00 | 14B | 25FD4 |
| 26 | 1 | 0 | 0 | 0B7 | 41 | 14C | 25FDC |
| 2B | 1 | 0 | 0 | 0B8 | 01 | 14D | 25FE4 |
| 25 | 1 | 4 | 0 | 0B9 | 00* | 14E–151 | 25FEC |
| 90 | 1 | 4 | 0 | 0BD | 01* | 152–155 | 25FF4 |
| 39 | 1 | 46 | 0 | 0C1 | 00* | 156–183 | 25FFC |
| 38 | 1 | 46 | 0 | 0EF | 00* | 184–1B1 | 26004 |
| 3A | 1 | 46 | 0 | 11D | 00 | 1B2–1DF | 2600C |
| 32 | 2 | 48 | 4 | 14B | 3C* | 1E0–35F | 26014 |
| 35 | 1 | 48 | 4 | 2CB | 00* | 360–41F | 2601C |
| 33 | 1 | 46 | 4 | 38B | 40 | 420–4D7 | 26024 |
| 34 | 1 | 48 | 0 | 443 | 00 | 4D8–507 | 2602C |
| 91 | 2 | 30 | 4 | 473 | 00 | R | 26034 |
| 92 | 1 | 30 | 4 | 563 | 40 | R | 2603C |
| 93 | 1 | 30 | 4 | 5DB | 00 | R | 26044 |
| 94 | 1 | 4 | 0 | 653 | 80 | R | 2604C |
| 29 | 1 | 0 | 0 | 657 | 00 | 508 | 26054 |
| 2A | 1 | 0 | 0 | 658 | 00 | 509 | 2605C |
| 64 | 1 | 0 | 0 | 659 | 00 | R | 26064 |
| 27 | 1 | 0 | 0 | 65A | 00 | R | 2606C |
| 66 | 2 | 0 | 0 | 65B | 00 | R | 26074 |
| A0 | 1 | 0 | 0 | 65D | 00 | 50A | 2607C |
| 2D | 6 | 0 | 0 | 65E | 00 | R | 26084 |
| D2 | 7 | 0 | 0 | 664 | 00 | R | 2608C |
| D5 | 1 | 0 | 0 | 66B | 00 | R | 26094 |

**Verified:** An asterisk marks a default override in `0x205CC`.
Multi-byte fields default to zero unless explicitly overridden.

| ID | Effective default | Evidence |
|---|---|---|
| 01 | 3 for channels 10–11, 2 otherwise | Verified: `0x205CC` |
| 02 | 30 for channel 8, 0 otherwise | Verified: `0x205CC` |
| 09 | `2*p1` for 0–5, `54` for 6, `2*(p1+1)` for 7–14, `FF` for 15–16 | Verified: `0x20520` |
| 15 | `30+2*p1` for 0–14, `30` for 15–16 | Verified: `0x2056C` |
| 25 | `13 12 16 04` | Verified: flash `0x2617C`, RAM `0x1FFF8EAC`, `0x205CC` |
| 90 | 1 for mixers 0–2, 0 for mixer 3 | Verified: `0x205CC` |
| 39 | 0 for channels 0–11, 1 for 12–45 | Verified: `0x205CC` |
| 38 | 1 for channels 0–8, 10–11, 30–31. Zero otherwise | Verified: `0x205CC` |
| 32 | Big-endian 600, except channels 8–9 and mixer 3 channels 30–45: zero | Verified: `0x205CC` |
| 35 | 1 for channels 8–9, 0 otherwise | Verified: `0x205CC` |

**Verified:** Runtime route reset also writes state through separate handlers (`0x139C8`, `0x13AE0`).
Do not confuse raw factory-default bytes with the post-replay hardware routes.

### Store and notification semantics

| Operation | Reports | Save trigger | Evidence |
|---|---|---|---|
| `0x20820`, one-byte setter | Source 0 and changed value mark pending bit | Changed value, source not 2, nonvolatile, ID not `23` | Verified: `0x20820` |
| `0x20918`, descriptor-width setter | Source 0 always marks pending bit if supported | Always, source not 2, descriptor flag zero, ID not `23` | Verified: `0x20918` |
| Source 1 host set | No generic echo | As above | Verified: `0x20820`, `0x20918` |
| Source 2 replay | No generic report | No save trigger | Verified: `0x20820`, `0x20918` |

**Verified:** An unchanged host write can postpone persistence because the descriptor-width setter still resets the save timestamp (`0x20918`).
Command `23` participates in every full save, but cannot trigger one alone (`0x20918`, `0x20F5C`).
Group updates to other channels use source 2 and do not independently report or trigger persistence (`0x17020`).
A subsequent save still includes those changes.

### Reports

**Verified:** The 28-entry pending-report table starts at RAM `0x1FFF8DCC`, initialized from flash `0x2609C`.
Each eight-byte entry holds command ID at offset 0 and a 32-bit pending-p1 mask at offset 4 (`0x21854`, `0x2153C`).
Its exact order is:

`11 02 03 12 13 14 10 16 01 04 05 06 08 07 0A 28 42 19 29 27 40 43 52 53 61 64 D2 D5`.

**Verified:** Get requests for every other ID do nothing (`0x208E0`, `0x21854`).
Supported Get requests ignore p2 and set `1<<p1` without a dimension check.
The actual Thumb register shift yields zero for p1≥32 (`0x20904–0x20910`).
Indices within 0–31 but outside a descriptor count leave pending bits that normal traversal cannot clear (`0x2153C`).

**Verified:** The pending sender forces p2=0 (`0x2159A–0x2159E`).
It emits type 1 when width=1 and p2 count=0, otherwise type 2 (`0x15A10`).
Record size is `ceil((5+width)/4)` words for type 2 (`0x159A4`).
The pending bit clears before mailbox send, and the caller ignores send failure (`0x215C2`, `0x15668`).
**Inferred:** A send failure can lose a notification.

**Verified:** Get-all order is version preamble, persistent descriptors in table order, completion, then lock reports (`0x15668`).
Pending reports already queued can precede the version preamble.
The persistent iterator varies p1 fastest, then p2 (`0x213C4`).
The descriptor table yields 927 persistent records. The fixed preamble, completion, and lock reports add nine records.

| ID | Content | Evidence |
|---|---|---|
| 40, p1=0 | `01 05 03`, PSoC version | Verified: `0x17404` |
| 40, p1=1 | FPGA bytes `05,06`, then zero | Verified: `0x17404` |
| 40, p1=2 | `(FPGA[02]>>3 & 7)+1`, then two zeros | Verified: `0x11B4C`, `0x17404` |
| 40, p1=3 | Zero, resource version from `1C5A4`, resource check byte from `1C5D4` | Verified: `0x17404` |
| D2 | FPGA bytes `1807–180C`, then zero | Verified: `0x17404` |
| 41 | Eight UID bytes requested, but final message carries only seven | Verified: `0x11B74`, `0x15C50`, serializer bug below |
| 44 | Type 2, length 2, bytes `01` and low byte of `0x1FFF9148`, then reset that variable | Verified: `0x15668` |
| 42 | External lock: PLL locked and measured rate within inclusive ±5% of requested rate | Verified: `0x15F58`, `0x21670` |
| 64 | Inverse of FPGA status bit 6, when clock source is external | Verified: `0x16026–0x16064` |
| D5 | FPGA byte `180E`, report on change | Verified: `0x16118`, `0x136E4` |
| 43 | Power state | Verified: `0x15FDE`, `0x17660` |
| 61 | Update result code and CRC | Verified: `0x18198` |
| 52,53 | Functional-test result bytes | Verified: descriptors. Meaning deferred to front-panel report |

**Unknown:** `0x1FFF9148` has no nonzero writer in the examined application references.
Its intended completion-status meaning remains unknown (`0x153C4`, `0x15668`).

**Verified:** `0x15B48` writes complete record bytes but returns `2+floor((len-3)/4)` words for len>3.
The return lacks a remainder increment (`0x15BF6–0x15C0A`).
For UID length 8, it returns three words for a four-word record.
The preamble therefore sends 16 words, not 17. UID data byte 7 lies outside the transmitted length (`0x15C50`).
This is a serializer-length defect, not a seven-byte UID-read loop.

**Verified — prior device test:** `probe-results.md`, “Get-all”, records 936 reports per request.
Its kernel-panic section records the vendor kext overread caused by the truncated UID report.
Those tests predate this static map. They do not validate malformed-input or EEPROM-edit behavior.

**Unknown — source discrepancy:** The prior probe summary labels `90` as type 2.
This image's descriptor and serializer select type 1 (`0x25FF4`, `0x15A10`).
Raw captured packets are required to resolve that discrepancy.

## EEPROM persistence

### On-device layout

**Verified:** `0x20F5C` and `0x210B0` select descriptors with volatile bit 0 clear.
This image writes 42 descriptors, 1119 data bytes, and a four-byte header: 1291 bytes total, ending at offset `0x50B`.

| EEPROM offset | Size | Content | Evidence |
|---|---:|---|---|
| `000` | 1 | Magic `AE` | Verified: `0x20F5C`, `0x20BF0` |
| `001` | 1 | Schema version `02` | Verified: `0x20BF6` |
| `002` | 1 | Descriptor count, current value `2A` | Verified: `0x20F5C`, table calculation |
| `003` | 1 | CRC over descriptors and data, excluding header | Verified: `0x20F5C`, `0x20B78` |
| `004–0AB` | 168 | Forty-two four-byte descriptors: ID, width, p1 count, p2 count | Verified: `0x20EEC`, `0x20AD4` |
| `0AC–50A` | 1119 | Persistent values, in descriptor order | Verified: `0x20F5C`, table above |
| `50B–7EF` | 741 | Unused by current settings writer. Content not defined | Verified boundary: `0x20F5C`. Unknown content |
| `7F0–7F3` | 4 | Power marker: `CD AB bool 00` | Verified: `0x17704`, `0x17754` |
| `7F4–7FF` | 12 | Preserved by partial-row writer, purpose unknown | Verified: `0x13188` |

**Verified:** RAM temporary descriptors reside at `0x1FFFA870`, with eight-byte stride.
Only their first four bytes come from EEPROM. Offset 4 receives a computed data offset (`0x20B78`).
The save path keeps state-pool offsets separately at `0x1FFFA7BC` (`0x20F5C`).

**Verified:** CRC state starts at zero (`0x218CC`).
For each byte, `0x218EC` computes `t=(crc^byte)<<8`, then repeats eight steps:

```text
if t & 0x8000:
    t ^= 0x8380
t = (t << 1) & 0xffff
crc = t >> 8
```

**Verified:** Instructions `0x21924–0x2192E` express the XOR as XOR `0x7C7F`, then complement.
The equivalent byte algorithm is unreflected CRC-8, polynomial `0x07`, initial value zero, no final XOR.
The header is not covered. CRC cannot establish origin or reject deliberate edits.

### Save and replay sequence

| Function | Role | Evidence |
|---|---|---|
| `20498` | Advance active save, then start a new save if dirty age exceeds 3000 timer counts | Verified: `0x2049C–0x204D0` |
| `210B0` | Build persistent descriptors, write header with CRC zero and first three descriptors, select state 1 | Verified: `0x210B0` |
| `211DC`, state 1 | Append one descriptor per call | Verified: `0x211DC` |
| `211DC`, state 2 | Append up to 16 live state bytes per call and update CRC | Verified: `0x211DC` |
| `211DC`, state 3 | Patch header CRC, then clear active state | Verified: `0x211DC` |
| `20F5C` | Synchronous equivalent for factory reset | Verified: `0x20F5C` |
| `204DC` | Finish an active save only. Does not start a merely dirty save | Verified: `0x204DC` |
| `13050/130AC` | Buffer bytes at `0x1FFF9088`, flush each full 16-byte row | Verified: `0x13050`, `0x130AC` |
| `1314C/13188` | Flush partial row or patch bytes with read-modify-write | Verified: `0x1314C`, `0x13188` |
| `23064` | Program one EEPROM row. Return status is ignored by application writers | Verified: `0x13050`, `0x130AC`, `0x13188`, `0x23064` |
| `20B78` | Validate magic, version, count≤44, aggregate payload<`7F0`, and CRC | Verified: `0x20BF0–0x20CCE` |
| `20D18` | Read each EEPROM value, store using current descriptor, return command for source-2 dispatch | Verified: `0x20D18`, caller `0x15F58` |

**Verified:** The async writer reads the live state pool, not an immutable snapshot (`0x211DC`).
A concurrent host or panel change can produce values from different times in one valid-CRC save.
The loop uses one EEPROM copy, not alternating banks or a journal (`0x210B0`, `0x211DC`).
The first row contains CRC zero until the final patch (`0x210B0`, `0x211DC`).

**Inferred:** Power loss during a save can invalidate the saved configuration.
CRC zero is not a guaranteed invalid marker, so an interrupted image can also pass by coincidence.
EEPROM write failures can remain silent because callers discard row-write status (`0x13050`, `0x13188`).

**Verified:** Invalid EEPROM normally leaves initialized defaults and advances the periodic state to run (`0x203B4`, `0x15F58`).
It does not automatically rewrite EEPROM on that path.
A malformed schema that passes validation is different: replay trusts fields before any per-command safety check.

### Instruction-confirmed replay weaknesses

| Input defect | Actual check and consequence | Evidence |
|---|---|---|
| Count zero | Accepted when CRC is zero. Replay still reads descriptor zero before count test | Verified: `0x20BFE`, `0x20D3A–0x20D4C`, final count check `0x20E9C` |
| Payload near EEPROM end | Validator checks payload sum alone, not `4+4*count+payload` | Verified: `0x20C52–0x20C58`, CRC reads `0x20C96–0x20CA6` |
| Oversized value width | Replay checks start<`7F0`, then copies the full descriptor width without end or destination bound | Verified: `0x20DCA–0x20E06` |
| Unknown or mismatched command | No persistent-command allowlist or width match before replay dispatch | Verified: `0x20D48`, `0x20E10`, caller `0x15F58` |
| Unknown settings ID | Prefill read can fail, but its return is ignored before EEPROM copy | Verified: `0x20D62–0x20D64` |
| Descriptor size zero | No bytes copied. Replay can dispatch stale or default-prefilled command data | Verified: `0x20DFC–0x20E06` |
| Invalid descriptor flag | Replay tests byte 7 of RAM descriptors, although EEPROM supplies only bytes 0–3 | Verified: `0x20AD4`, `0x20E8A–0x20E92` |

**Verified:** The periodic caller supplies a 112-byte internal-command buffer (`0x15F58`, stack layout).
Data begins at offset 11, so at most 101 bytes fit.
An EEPROM width of 102–255 can overwrite caller stack state (`0x20DF4`).
For example, a one-descriptor schema with width 255 passes the aggregate-size check.

**Inferred:** A deliberate valid-CRC EEPROM edit can reach update/reset commands through source-2 dispatch, not only saved-setting handlers.
A corrupt or malicious descriptor can also overwrite the stack before dispatch.
No device test established recovery behavior. Do not treat EEPROM edits as safe configuration changes.

## Safety notes

- **Verified:** Do not send slot length 31. The final copied word overwrites a timer callback (`0x120B8`, destination `0x1FFFA0A8`).
- **Verified:** Do not send output p1 above 2. Commands `11–13` write outside their three-entry state array (`0x14BC2`, `0x14C18`, `0x14C6C`).
- **Verified:** Do not rely on type-2 length checks. Lengths 100–255 still dispatch stale bytes (`0x155C0–0x155CE`).
- **Verified:** Do not edit EEPROM descriptors without an offline validator. Replay can overwrite the stack (`0x20DF4`).
- **Verified:** Do not invoke update commands for protocol discovery. Dispatcher cases `60–63` enter update or power-control code (`0x16F2A–0x16F70`).
- **Inferred:** Do not test arbitrary routes with live outputs. Unchecked route codes and DSP routes can create feedback (`0x13DFC`, `0x1421C`).
- **Verified:** Do not assume settings saves are atomic. The application rewrites one EEPROM image and patches its CRC last (`0x210B0`, `0x211DC`).
- **Verified — prior test:** Avoid Get-all through the vendor kext. `probe-results.md` records a kernel panic from the UID-report overread.

## Coverage gaps and proposed tests

**Verified — offline checks:** The report's 60 descriptor rows match the binary.
All 151 name entries have unique addresses. Every function name corresponds to a baseline function entry.
The tool passed Python syntax compilation, without bytecode output.
All 65,536 CRC-state/byte pairs match the byte-polynomial implementation.
These checks validate the map, not firmware execution.

| Gap | What remains unknown | Safe next action |
|---|---|---|
| FPGA event mediation | Restart event source, magic-word validation, and host/PSoC bit correspondence | Inspect FPGA logic. No BAR access |
| Timer units | Exact time per counter tick | Trace timer component clock setup and configuration tables |
| Hardware ranges | Complete low-level effects of invalid mixer, DSP, and UI values | Use the audio/front-panel maps. Preserve dispatcher limits above |
| Update bounds | Complete update recovery and flash-write behavior | Use the update map. No updater run |
| EEPROM contents | Actual device bytes and interruption recovery | No device read or write was authorized |
| Invalid pending p1 | Exact stale-report sequence after unsupported pending mask bits | Build an offline instruction harness before any device experiment |
| Write interruption | Precise behavior after silent row-write failure or power loss | Model EEPROM rows offline. Do not interrupt device power |

**Proposed test — static, no device risk:** Reproduce the schema and EEPROM offsets:

```sh
python3 scripts/firmware/psoc-protocol-map.py
```

**Proposed test — static, no device risk:** Reproduce the malformed parser and EEPROM-copy instruction evidence:

```sh
uv run --with capstone scripts/firmware/psoc-protocol-map.py 153f8 15668
uv run --with capstone scripts/firmware/psoc-protocol-map.py 20d18 20eb8
```

**Unknown — device validation:** No live malformed-input test is proposed.
The demonstrated write primitives, update entry points, and vendor kext defect make such tests unsafe without a separate recovery plan.
