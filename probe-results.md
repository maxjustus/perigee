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
