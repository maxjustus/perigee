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
