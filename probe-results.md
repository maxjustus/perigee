# Probe results

Results of the probe in `plan.md` section 2. The `probe/` tool reads BAR0
through `AccessBAR0Register` (user client method 6) of the vendor kext.

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

The position-from-hardware design in `plan.md` section 3 holds. The
position resolution equals the DMA burst depth.

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
| 0x41 | 00 0D 6A 00 84 44 F1 00 | `data[0]` = 0: no external clock lock. `data[1..6]` equal bytes 1 to 6 of the Hardware UID, little-endian. `data[7]` was 0x00, then 0x08 |
| 0x29 | 01 | 48 kHz. This agrees with the ring-pointer rate |
| 0x2A | 00 | Clock source 0 |
| 0x42 | 01 | Device ready. Last report before 0x64 |

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
