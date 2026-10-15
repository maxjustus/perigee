# Probe results

Hardware results, oldest first. The early sections use the `probe/` tool.
It reads BAR0 through `AccessBAR0Register` (user client method 6) of the vendor kext.

## Setup

| Item | Value |
|------|-------|
| Host | macOS 27.0 (26A428), arm64, SIP disabled |
| Kext | `com.apogeedigital.kextElementEnsemble` 0.8.7 |
| PCI | `pci19c2,2201`, revision 0x56, BAR0 32 KB, MSI |
| Channels | 34 in, 36 out (kext properties) |

## Second user client

The vendor HAL (`coreaudiod` pid 352) holds a user client. The kext does not
refuse a second `IOServiceOpen`. It replaces the device's client:

- `ElemEnsUserClient::start` calls `updateUserClient(this)`. This
  reinitializes the PSoC message buffer and starts meter DMA.
- `ElemEnsUserClient::clientClose` calls `updateUserClient(NULL)` and
  `stopHardware()`. This stops meter DMA and audio DMA for every client.

`AccessBAR0Register` does not require method 0 (`Open`). Method 0 calls
`IOService::open` on the device and fails while the HAL holds it.

Consequences:

- A probe client cannot sample registers while the vendor HAL plays audio.
  The close stops the stream. Step 3 of the probe must start the hardware
  from the probe client, with the vendor HAL idle.
- After a probe run, the device has no client pointer. Restart `coreaudiod`
  to give the vendor HAL its client back.

## Idle registers

The device was idle (`kAudioDevicePropertyDeviceIsRunningSomewhere` = 0).
The probe client's `start` enabled meter DMA before the reads.

| Offset | Register | Value | Decoded |
|--------|----------|-------|---------|
| 0x00 | ID | 0xabcdef01 | Constant pattern, not a version |
| 0x0C | GENERAL | 0x28000000 | Bits 27, 29: meter DMA arm and run. Bit 30 clear: 62.5 MHz core clock |
| 0x10 | STATUS | 0x00000000 | |
| 0x14 | INTERRUPT | 0x00000000 | No MSI enabled |
| 0x68 | INFO | 0x00000050 | Bits 7:6 = 1: PSoC bootloader status valid. Bit 4 not decoded |

## Ring pointers

`probe ring` calls `StartHardware` with depth 2 and the vendor HAL idle. It
reads `CUR_OUTPUT_AUDIO_ADDRESS_LOW` and `CUR_INPUT_AUDIO_ADDRESS_LOW` about
every 1 ms for 5 seconds. The client close stops the hardware.

| Ring | Base (LOW register) | Out of range | Backward | Wraps | Frames/s | Step GCD |
|------|---------------------|--------------|----------|-------|----------|----------|
| Output | 0x80000000 | 0 | 0 | 14 | 48000.96 | 288 bytes |
| Input | 0x00000000 | 0 | 0 | 14 | 48000.96 | 272 bytes |

Findings:

- The address registers read back the ring IOVA. They are not write-only.
- Both `CUR_*` registers are live during the stream. They advance
  monotonically and wrap at `channels * 0x4000 * 4` bytes from the base.
- The step GCD is 2 frames in both rings (288 = 2 * 36 * 4,
  272 = 2 * 34 * 4). The pointer moves in bursts of `SAMPLEDEPTH + 1`
  frames.
- The unit runs at 48 kHz. 5 seconds give 14 wraps of 16384 frames.

A driver can read the stream position from the hardware. The position
resolution equals the DMA burst depth.

## Interrupt bits

`probe irq [mask]` enables timestamps (`MiscRequest` type 6), maps the
timestamp page (memory type 2), and starts the stream with depth 2. It ORs
the mask into `INTERRUPT` for 2 seconds, then restores the register. The
kext adds 0x4000 to `sampleTime` for each MSI, so `sampleTime / 0x4000`
counts the MSIs. The probe reads it every 1 ms.

| `INTERRUPT` | MSIs in 2 s | Times (ms), MSIs at each time |
|-------------|-------------|------------------------------|
| 0x01000000 (bit 24) | 5 | 341, 683, 1024, 1365, 1706. 1 each |
| 0x01400000 (bits 24, 22) | 10 | 341, 682, 1024, 1366, 1707. 2 each |
| 0x05000000 (bits 24, 26) | 5 | 341, 683, 1024, 1365, 1707. 1 each |

Findings:

- Bit 24 gives one MSI per ring wrap: 16384 frames at 48 kHz = 341.3 ms.
- Bit 22 gives a second MSI within 1 ms of each wrap. It is probably the
  wrap of the other ring. Both rings wrap at the same time.
- Bit 26 gives no MSI during a normal stream. It can be an error
  interrupt. This is unverified.
- No bit gives a shorter interrupt period. The `CUR_*` registers are the
  only source of position between wraps.

## Hot unplug

A loop ran `probe ring` with the vendor HAL off. The Thunderbolt cable was
pulled with the unit powered on, then reconnected. Log:

    16:11:07.179
    probe: register reads 0xffffffff: device gone
    16:11:07
    probe: no "com_apogeedigital_Ensemble2Device" in the IORegistry

- `IOServiceOpen` succeeded. The next BAR0 read through the kext returned
  0xFFFFFFFF, not an IOKit error.
- Less than 1 second later, the device was gone from the IORegistry.
- After reconnect, the kext matched a new device instance. No panic.
- The unplug came between two probe runs, before `StartHardware`. Reads in
  the middle of a stream were not tested.

## Get-all

`probe getall` registers a Mach port with `IOConnectSetNotificationPort`.
It sends one type-4 packet through `SendRequest` and prints each
notification until 2 seconds pass with no notification. No host handshake
was necessary. The probe client did not call `Open`.

Each notification is a Mach message with `msgh_bits = 0x13` (copy send)
and `msgh_id = 0`. The body is one 120-byte packet.

Two runs gave 936 packets each, in the same order. The first packet came
after 22 ms, the last after 172 ms. Packets come in batches about 12.5 ms
apart.

Packet fields:

- The 8-byte header is 0 in all packets.
- Type-1 packets carry the value in `data[0]` with `len = 1`. Their `p2`
  is stale. It holds the `p2` of the previous type-2 packet.
- In mixer packets (0x32 to 0x3A), `p1` is the channel (0 to 47) and `p2`
  is the mixer (0 to 3).

Order of command IDs, with packet count and type:

| Order | IDs |
|-------|-----|
| Status | 0x40 x4 (2), 0xD2 x1 (2), 0x41 x1 (2) |
| Inputs | 0x01 x12, 0x03 x12, 0x02 x9, 0x07 x12, 0x04 x8, 0x05 x8, 0x06 x8, 0x08 x8, 0x0A x2 |
| Routing and outputs | 0x09 x17, 0x1C x2, 0x1D x2, 0x0F, 0x0D x10, 0x0E x10, 0x11 x3, 0x12 x3, 0x13 x3, 0x14 x3, 0x1A x2, 0x10, 0x16 x2, 0x15 x17 |
| Front panel | 0x20, 0x21, 0x22, 0x23, 0x24, 0x26, 0x2B, 0x25 x4, 0x90 x4 (2) |
| Mixer | 0x39 x46, 0x38 x46, 0x3A x46, 0x32 x192 (2), 0x35 x192 (2), 0x33 x184 (2), 0x34 x48 |
| Clock | 0x29, 0x2A, 0xA0 |
| End | 0x44 x1 (2), 0x42, 0x64 |

IDs without a type mark are type 1.

Decoded values:

| ID | Data | Reading |
|----|------|---------|
| 0x40 p1 0 | 01 05 03 | Probably PSoC firmware 1.5.3 |
| 0x40 p1 1 | 00 56 00 | 0x56 equals the PCI revision (FPGA firmware) |
| 0x41 | 00 0D 6A 00 84 44 F1 00 | Unit ID: `data[1..6]` equal bytes 1 to 6 of the Hardware UID, little-endian. `data[7]` was 0x00, then 0x08 |
| 0x29 | 01 | 48 kHz. This agrees with the ring-pointer rate |
| 0x2A | 00 | Clock source 0 |
| 0x42 | 01 | External clock lock: locked (see notes 5.7) |

Differences from the notes:

- 0x34 (MixerChannelSolo) arrives as type 1, one packet per channel.
- 0x09, 0x44, 0x64 (as a Get-all report), and 0xD2 are not in the notes.

## Power cycle with the vendor HAL loaded

The unit was disconnected, powered off, powered on with no host, and
reconnected. The vendor HAL attached to the new device before the probe
ran. The HAL restores a settings snapshot on connect, so this diff mixes
the power-on state with that restore.

The Get-all after the cycle had the same 936 packets in the same order.
Only mixer flags changed, plus the volatile last byte of 0x41:

| ID | Before | After |
|----|--------|-------|
| 0x39 IsStereo | Channels 2 to 5 set | Clear |
| 0x38 IsVisible | 12, 13 clear. 14 to 21 set | 12, 13 set. 14 to 21 clear |
| 0x35 Mute, mixers 0 to 2 | Different per mixer | Channels 8, 9 only, as in mixer 3 |

All other settings kept their values: input types, gains, routing, output
levels, sample rate, and clock source. A cycle with the vendor HAL removed
must separate the power-on state from the HAL restore.

## Power cycle with the vendor HAL off

`scripts/vendor-hal.sh off` removed the vendor HAL. The probe took a
Get-all, the unit was power-cycled with no host and reconnected, and the
probe took a second Get-all. No other software wrote to the unit.

The two runs had the same 936 packets with the same values. Only the stale
`p2` of type-1 packets differed.

Consequences:

- The unit keeps every setting that Get-all reports across a power cycle.
- The mixer changes in the cycle with the vendor HAL loaded came from the
  HAL restore, not from the unit.
- A driver that skips the restore gets the last state that the unit was
  given. The driver does not need to restore settings at attach.

## Kernel panic in the vendor kext

The Mac panicked during repeated `coreaudiod` restarts. Each restart makes
the vendor HAL send a Get-all. Report:
`/Library/Logs/DiagnosticReports/panic-base+socd-2026-10-12-155210.000.panic`.

- Kernel data abort. Probabilistic guard malloc reports an out-of-bounds
  read, 1 byte past a 64-byte element of `kalloc.type.var6.64`.
- Backtrace: `_messagingProtocolTimerHandler` + 0x118, then
  `_processPropertyNotificationFromHardware` + 0x110, then `memcpy`.

At `_processPropertyNotificationFromHardware` + 0xF0 the kext copies a
type-2 record with `memcpy(packet + 13, record + 5, min(len, 100))`. It
does not limit the copy to the words that remain in the message.

The registers at the panic match the first Get-all message. `x25` = 13 is
the word index of the record. In that message, 0x40 x4 fill words 2 to 9
and 0xD2 fills words 10 to 12. So 0x41 starts at word 13. With
`len = 8`, the copy reads bytes 57 to 64 of a 64-byte (16-word) message.
Byte 64 is outside the buffer.

Consequences:

- The PSoC sends 7 data bytes for 0x41 but sets `len = 8`. `data[7]` of
  0x41 is heap memory. This is why it changed between runs.
- Each Get-all reads past the buffer. The guard samples few allocations,
  so most reads pass. Each Get-all through the vendor kext carries a small
  risk of a panic.
- A new driver must limit each record to the message length.

## Identity reports through the open driver

2026-10-13, after commit `e2c39cd`. `scripts/firmware/device-reports.py`
sent one type-3 Get per report ID through `raw.send` of ensemble-control.
The vendor kext was not loaded. Seven tests for the client are in
`scripts/firmware/device-reports-test.py`. Output:

| Query | Data | Reading |
|-------|------|---------|
| 0x40 p1 0 | 01 05 03 | PSoC firmware 1.5.3, matches the vendor file |
| 0x40 p1 1 | 00 56 00 | FPGA firmware 0.56, matches the vendor revision |
| 0x40 p1 2 | 03 00 00 | Hardware revision 3 |
| 0x40 p1 3 | 00 06 1B | Resource version 6, whole-file CRC-8 `0x1B` |
| 0x41 | 00 0D 6A 00 84 44 F1 | Unit ID, 7 bytes |
| 0x42 | 01 | External clock locked (Internal source) |
| 0x64 | 01 | PLL locked |
| 0xD5 | 162 | DSP cycles per sample per thread at 48 kHz |
| 0xD2 | 01 00 00 01 00 00 00 | DSP core version |

`front-panel-resources.py` computes CRC-8 `0x1B` over the vendor
`EnsembleResourceData.bin`. The device reports the same value, so the
resource partition in external flash matches the vendor file at CRC-8
confidence. An 8-bit check cannot rule out a crafted collision, but it
rules out ordinary corruption.

One Get of 0x40 returns all four selector reports, not only the selector
that the p1 byte names. Lock reports 0x42 and 0x64 arrived five times each
within one 4 s window, so the device repeats them outside an explicit
request. The tracker for this work is
`.pi-html/artifacts/_project/apogee-ensemble-driver/firmware-map-v001.html`.

### Firmware release status

2026-10-14. The Apogee knowledge base lists the final Ensemble Thunderbolt
firmware as PSoC 1.5.3, FPGA 0.56, and resource 6. The base rate above
matches. The installed firmware is the final vendor release. See
`docs/firmware/vendor-evidence.md`.

### Passive stream and Get-all through the open driver

2026-10-14, `scripts/firmware/device-reports.py`, open driver, no vendor kext.

R4, passive log for 45 s: 1,242 notifications, all `meters`. With no
request outstanding the device sends meter frames and nothing else.
The repeated lock reports seen earlier followed our own Gets.

R5, one type-4 Get-all with an 8 s window: 85 reports across 21 command
identifiers: 0x01, 0x03, 0x07, 0x09, 0x25, 0x26, 0x32 to 0x35, 0x38,
0x39, 0x3a, 0x40, 0x41, 0x42, 0x44, 0x64, 0x90, 0xa0, 0xd2.
Every identifier also appears in the vendor-kext capture.

The 0x41 unit-ID record arrived as seven data bytes
`00 0d 6a 00 84 44 f1`. The vendor-kext capture of the same record
carries eight bytes, with the extra byte from adjacent heap memory. That
overread is the panic cause recorded above. The open driver returns the
declared seven bytes, and the record parses without error.

Driver limit found: `validMessage` in `driver/EnsembleDriver/Protocol.h`
accepts types 1, 2, and 4 only, so a type-3 Get is refused with
`kIOReturnBadArgument`. The identity queries in `device-reports.py` and
the DSP query path in `scripts/dsp/dsp.py` need type 3, so both fail on
the current driver. `kDeniedCommands` also blocks 0x60 to 0x63, which
keeps the bootloader entry command out of reach until the driver allows
it. Bootloader session R7 additionally needs the FPGA remote-I2C engine,
which the open driver does not implement.

### Message types and restored identity reads

2026-10-14. `validMessage` in `driver/EnsembleDriver/Protocol.h` now accepts
types 1 to 4, so a type-3 Get passes. `driver/tests/protocol_test.cpp`
asserts acceptance of type 3 and rejection of a trailing word after it.

With the rebuilt dext active, every identity query works again:
PSoC 1.5.3, FPGA 0.56, hardware revision 3, resource version 6 with
CRC-8 `0x1B`, clock and PLL locked, DSP cycle count 162, DSP core version
`01 00 00 01 00 00 00`.

The unit-ID Get is the exception. A direct type-3 Get for 0x41 returns
nothing, twice with an 8 s window. The identifier arrives inside a Get-all
response instead. The earlier unit-ID answers came from the report burst
that a 0x40 Get triggers, not from a direct Get.

The `kDeniedCommands` list still blocks 0x60 to 0x63, and the driver has
no remote-I2C engine. The bootloader session therefore remains out of
reach.

## Bootloader check stage

2026-10-14, 17:14, `ensemble-bootloader check` on the open driver at
commit `f70b44e`. The plan is in `docs/firmware/bootloader-options.md`.

The run took 5.4 s and exited with status 0. The Enter reply was
`69 f0 12 2e 00 14 01 01`:

| Bytes | Reading |
|-------|---------|
| `69 f0 12 2e` | Silicon ID 0x2E12F069, little-endian. It matches the CYACD header |
| `00` | Silicon revision 0 |
| `14 01 01` | Bootloader version bytes |

Enter with no data succeeded, so the loader has no security key. Exit
returned the unit to status 1 without a reply read.

After the session, two Get-alls returned no report, while meter frames
continued. The PSoC application ran, and the front panel looked normal. A
dext restart reset the mailbox, and the next Get-all returned 936 reports.
Without the stale `p2`, they are identical to the Get-all before the
session. The session changed no setting.

Cause: the PSoC takes the host only after a mailbox reset that it sees
with its FPGA event interrupt on. Its startup writes status 1 before that
interrupt is on (`docs/firmware/psoc-protocol.md`). The dext reset came
too early. Commit `18e29e4` resets the mailbox again each second until a
report arrives, and it treats a return to status 1 as a restart.

### Second check with the mailbox fix

2026-10-14, 17:32, the same check on commit `e6890f6`. The reply was the
same 8 bytes. The dext kept its process, PID 23054.

| Time after Exit | Get-all result |
|-----------------|----------------|
| 2 s | No report |
| 4 s | 943 reports. Input types (0x01) and mic gains (0x02) differ from the baseline |
| 13 s | 941 reports, still different |
| 29 s and later | 936 reports, identical to the baseline without `p2`. Three reads agree |

The mailbox fix works: the PSoC answered within 4 s, with no dext restart.

The application reports startup values for about 30 s after a restart:
input types 0x02 and mic gains 0 on inputs 1 to 8. Then it reports the
stored settings. The extra reports in the early reads overlap the
Get-all that the dext sends at the restart. The dext restart Get-all can
therefore give clients startup values. The ensemble-control cache showed
the stored values afterwards, but the later Get-alls also updated it.
Whether the application sends the stored values without a request is
unknown.

## Bootloader scan stage

2026-10-14, `ensemble-bootloader scan`, commit `95faa2b`. The scan file is
`.pi-html/artifacts/_project/apogee-ensemble-driver/bootloader-scan-20261014-1749.json`.

The first run, at 17:47, stopped after 6.9 s with `badMarker`. That build
did not record the bytes. The tool sent Exit, and the status read 1. The
second run, at 17:49, took 98 s. Its two passes agreed.

`scripts/firmware/bootloader-rows.py` results:

| Item | Result |
|------|--------|
| Silicon ID | 0x2E12F069 |
| Loader version | `14 01 01`: Cypress Bootloader component 1.20 |
| Report size | First row 0, last row 1023 for arrays 0 to 3 |
| Image rows | All 355 match the 288-byte row sums. 206 match the 256-byte sums. So ECC is off |
| Array 0 | Rows 0 to 69 nonzero, rows 70 to 255 zero. The loader uses 70 of its 256 rows |
| Array 2 | Rows 98 to 148 nonzero, outside the image. Probably rows of an older, larger application |
| Array 3 | Row 255, the metadata row, is the only nonzero row |
| EEPROM | 32 distinct row checksums. Row 0x7F, which holds the restart marker, sums to 0x87 |
| Loader fingerprint | SHA-256 of the array 0 checksums: `a50c5bbb9d9daba226b2d1800a27841cfa0f9efa9f70fc938c822f58d4038304` |

A Get-all 20 s after Exit differed from the baseline. A Get-all 35 s after
Exit was identical to the baseline without `p2`.

Consequence for a future update: the 1.20 report-size reply does not show
a protected loader region. The 1.60 reference refuses program rows below
the loader end. The 1.20 guard is unknown, so no write may target array 0.

## Settings after a PSoC restart

2026-10-14, two check runs inside a passive 60 to 75 s log, with no other
Get-all.

Before `67b9569`: the dext Get-all at the restart, 3 s after it, returned
start-up values. Report 0x43 = 1 came 11 s after the restart, with no other
report. Two minutes later the ensemble-control cache still showed Mic and
gain 0 on inputs 1 to 8, while a fresh Get-all returned the stored values.

After `67b9569`: the restart Get-all came at 3 s, and a second Get-all came
at 11 s, after 0x43. The cache then held the stored values: +4dBu on inputs
1, 2, and 5 to 8, Instrument on inputs 3 and 4, and mic gains 0, 0, 0, 41,
45, 45, 7, 58.
