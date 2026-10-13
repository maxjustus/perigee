# Apogee Ensemble Thunderbolt: vendor driver analysis

Source: the driver installed on this Mac, version 0.8.7, built 2022-07-25.

- Kext: `/Library/Extensions/ApogeeElementEnsemble.kext` (x86_64 + arm64e)
- HAL plugin: `/Library/Audio/Plug-Ins/HAL/ApogeeElementEnsemble.driver`
  (x86_64 + arm64)

Method: `otool -tV` on the x86_64 slices, plus symbol names and strings.
Every offset and bit in this document comes from the disassembly. Items
that the disassembly does not settle are marked "unverified".

Related files: `/tmp/apogee/kext.s` and `/tmp/apogee/hal.s` hold the full
disassembly. Regenerate them with `otool -arch x86_64 -tV <binary>`.

---

## 1. Architecture

The unit is a PCIe endpoint behind a Thunderbolt bridge. The FPGA exposes one
memory BAR (BAR0). A PSoC microcontroller handles all device settings. The
FPGA moves audio by DMA into host memory.

The vendor updater (`Apogee Firmware Updater.app`) holds the FPGA and PSoC
images, and they identify the parts:

| Part | Evidence |
|------|----------|
| FPGA: Intel (Altera) Cyclone V GX 5CGXC3 | `E2FPGA.bin` holds 14,510,912 bits. The Cyclone V datasheet (CV-51002, table 63) lists this uncompressed .rbf size for the C3 only. The GX variants carry the PCIe hard IP. An Audiofader review of the unit also names a Cyclone V |
| Microcontroller: Cypress PSoC 5LP, Arm Cortex-M3 | `EnsemblePSoC.cyacd` header: silicon ID 0x2E12F069. The application starts at flash address 0x10000 |
| PSoC to FPGA link | The PSoC External Memory Interface, 8 bits wide, at 0x6080_0000 (5.13) |

`scripts/psoc-firmware.py` disassembles the PSoC firmware.

Two host components exist:

| Component | Role |
|-----------|------|
| Kext `com_apogeedigital_ElemEnsBaseDevice` | Maps BAR0, allocates DMA buffers, handles the MSI, relays PSoC messages |
| HAL plugin (`AudioServerPlugIn`) | Owns the audio format, copies samples into the DMA rings, exposes controls |

The kext does not link IOAudioFamily. It links only IOPCIFamily and the
kernel KPIs. This split maps 1:1 onto a DriverKit `PCIDriverKit` dext plus a
user-space HAL plugin.

### 1.1 Supported units

PCI vendor ID 0x19C2 (Apogee). One kext personality per model:

| Model | PCI device | IOClass | Out ch | In ch | Min. PCI revision for DMA |
|-------|-----------|---------|--------|-------|---------------------------|
| Ensemble Thunderbolt | 0x2201 | `com_apogeedigital_Ensemble2Device` | 36 | 34 | 0x56 |
| Element 24 | 0x2203 | `com_apogeedigital_Elements24Device` | 24 | 14 | 0x26 |
| Element 46 | 0x2204 | `com_apogeedigital_Elements46Device` | 24 | 16 | 0x26 |
| Element 88 | 0x2205 | `com_apogeedigital_Elements88Device` | 24 | 20 | 0x26 |

The PCI revision ID (config offset 0x08, low byte) is the FPGA firmware
version. If the revision is below the minimum, `_startDMA` refuses to run.

Personality flags: `IOPCITunnelCompatible = true`,
`IOPCIPauseCompatible = true`. Both are required for Thunderbolt devices.

### 1.2 Kext start sequence

`ElemEnsBaseDevice::start`:

1. `mapDeviceMemoryWithRegister(0x10)` maps BAR0.
2. `setMemoryEnable(true)`, `setBusMasterEnable(true)`.
3. Ring size = 0x4000 frames (16384). Property "Buffer Frame Size".
4. Find the MSI vector: the first interrupt index whose type has bit 16 set
   (`kIOInterruptTypePCIMessaged`).
5. `_initHardware` (section 1.3).
6. `registerService`, power management (section 6).
7. Publish properties: "Number of Output Channels", "Number of Input
   Channels", "Buffer Frame Size", "Number of Host Meters", "Version"
   (`v0.8.7`), "name", "Device UID", "Hardware UID".

`_initHardware`:

1. Read PCI revision ID into the firmware-version field.
2. Write `I2C_CTRL (0x18) = 0`.
3. Create the work loop, command gate, and the 10 ms message timer.
4. Allocate DMA buffers (section 4).
5. Initialize the PSoC message slots (section 5.3).
6. Create the MSI filter interrupt source, zero the timestamp page.
7. Write `NUMBER_OF_CHANNELS (0x64)`, `SAMPLEDEPTH (0x60) = 0x1F`,
   `OUTPUT_AUDIO_BUFFER_SIZE (0x40)`, `INPUT_AUDIO_BUFFER_SIZE (0x2C)`.
8. Start meter DMA if a user client is attached.

`_uninitHardware` stops all three DMA engines, zeroes both buffer-size
registers, clears `INTERRUPT` bit 24, reads `STATUS`, then frees buffers.

---

## 2. BAR0 register map

All registers are 32-bit, little-endian, at byte offsets from BAR0. Every
register write in the kext is followed by a read-back of the same register.

### 2.1 Control block (0x00 to 0x84)

| Offset | Name | Access | Notes |
|--------|------|--------|-------|
| 0x00 | ID | R | Read once in the bootloader-status path |
| 0x04 | SCRATCH1 | RW | |
| 0x08 | SCRATCH2 | RW | |
| 0x0C | GENERAL | RW | DMA enables, message doorbells, clock select. See 2.2 |
| 0x10 | STATUS | R | Read on uninit. Bits not decoded |
| 0x14 | INTERRUPT | RW | Bit 22, 24, 26 = MSI enables. Bit 24 = buffer-wrap interrupt. See 2.3 |
| 0x18 | I2C_CTRL | RW | Remote I2C engine. See 7 |
| 0x1C | NUM_HOST_METERS | RW | Bits 15:0 = meter count (device). Host writes count << 16 |
| 0x20 | METER_TIMER | W | Meter DMA period. See 4.4 |
| 0x24 | METER_ADDRESS_LOW | W | Meter buffer IOVA, low 32 |
| 0x28 | METER_ADDRESS_HIGH | W | Meter buffer IOVA, high 32 |
| 0x2C | INPUT_AUDIO_BUFFER_SIZE | W | inChannels * 0x4000 (frames * channels, not bytes) |
| 0x30 | INPUT_AUDIO_ADDRESS_LOW | W | Record ring IOVA, low 32 |
| 0x34 | INPUT_AUDIO_ADDRESS_HIGH | W | Record ring IOVA, high 32 |
| 0x38 | CUR_INPUT_AUDIO_ADDRESS_LOW | R | FPGA write pointer (not used by the kext) |
| 0x3C | CUR_INPUT_AUDIO_ADDRESS_HIGH | R | |
| 0x40 | OUTPUT_AUDIO_BUFFER_SIZE | W | outChannels * 0x4000 |
| 0x44 | OUTPUT_AUDIO_ADDRESS_LOW | W | Playback ring IOVA, low 32 |
| 0x48 | OUTPUT_AUDIO_ADDRESS_HIGH | W | Playback ring IOVA, high 32 |
| 0x4C | CUR_OUTPUT_AUDIO_ADDRESS_LOW | R | FPGA read pointer (not used by the kext) |
| 0x50 | CUR_OUTPUT_AUDIO_ADDRESS_HIGH | R | |
| 0x54 | UNIQUE_ID_LOW | R | Hardware UID, low 32 |
| 0x58 | UNIQUE_ID_HIGH | R | Hardware UID, high 32 |
| 0x5C | OVER_UNDER_FLOW | RW | Bit 0 = underflow, bit 1 = overflow. Write 0 to clear |
| 0x60 | SAMPLEDEPTH | W | DMA burst depth minus 1. See 4.3 |
| 0x64 | NUMBER_OF_CHANNELS | W | Bits 7:0 = outChannels / 2. Bits 23:16 = inChannels / 2 |
| 0x68 | INFO | R | Bits 7:6 = PSoC bootloader status (1 or 2 valid) |
| 0x6C | HOST_CONTROL | ? | Named in debug print only. Never written |
| 0x70 | BERT_STATE | R | Bit error rate test. Debug only |
| 0x74 | SINE_PEAK | R | Debug only |
| 0x78 | SINE_INCR | R | Debug only |
| 0x7C | SINE_CAPTUR | R | Debug only |
| 0x80 | MUSYNC_CSR | RW | Multi-unit sync. See 2.4 |
| 0x84 | MISC_FLAGS | R | Bit 31 = FPGA "sneaky" bit. Bits 7:0 = Symphony AIM value |

### 2.2 GENERAL (0x0C) bits

| Bit | Mask | Meaning |
|-----|------|---------|
| 5 | 0x0000_0020 | Reset PSoC message state. Set after slot init |
| 6 | 0x0000_0040 | Host-to-PSoC message doorbell. Set after each slot write |
| 21 | 0x0020_0000 | Output DMA arm |
| 23 | 0x0080_0000 | Output DMA run |
| 24 | 0x0100_0000 | Input DMA arm |
| 26 | 0x0400_0000 | Input DMA run |
| 27 | 0x0800_0000 | Meter DMA arm |
| 29 | 0x2000_0000 | Meter DMA run |
| 30 | 0x4000_0000 | Core clock select. Set = 125 MHz DMA clock, clear = 62.5 MHz |

`_startDMA(type, enable)` sets both bits of a pair to enable. To disable,
it clears only the "run" bit. The "arm" bit stays set.

| DMA type | Value | Bits | Address registers |
|----------|-------|------|-------------------|
| Output (playback) | 0 | 21, 23 | 0x44 / 0x48 |
| Input (record) | 1 | 24, 26 | 0x30 / 0x34 |
| Meter | 2 | 27, 29 | 0x24 / 0x28 |
| Input and output | 3 | 21, 23, 24, 26 | |

### 2.3 INTERRUPT (0x14) bits

| Bit | Mask | Kext enum | Meaning |
|-----|------|-----------|---------|
| 22 | 0x0040_0000 | MSI type 1 | Unverified. Never enabled by the kext |
| 24 | 0x0100_0000 | MSI type 2 | Ring-wrap timestamp interrupt |
| 26 | 0x0400_0000 | MSI type 3 | Unverified. Never enabled by the kext |

The kext sets bit 24 in `setHardwareRunningState(true)` when timestamps are
enabled, and clears it on stop, sleep, and unload.

### 2.4 MUSYNC_CSR (0x80) bits

| Bits | Meaning |
|------|---------|
| 7:0 | Write: pause count. Zero is rejected |
| 20:8 | Read: phase value (mask 0x1FFF after shift) |
| 23 | Read: pause in progress. Writes are rejected while set |
| 31:24 | Read: pauses remaining |

### 2.5 PSoC message area (0x400 to 0xBF0)

| Offset | Name | Owner | Notes |
|--------|------|-------|-------|
| 0x400 + n*0x78 | RX slot n data (n = 0..7) | PSoC writes | 120 bytes per slot |
| 0x7C0 + n*4 | RX slot n state | Both | Bits 4:0 = length in words, bit 5 = full |
| 0x7E0 | PSOC_EVENT | PSoC writes, host clears | Ensemble only. See 5.5 |
| 0x800 + n*0x78 | TX slot n data (n = 0..7) | Host writes | 120 bytes per slot |
| 0xBC0 + n*4 | TX slot n state | Both | Same layout as RX state |
| 0xBE0 | HANDSHAKE | Host writes | Host writes 0xABCD1234 on PSOC_EVENT bit 1 |
| 0xBE4 | RX_WRITE_INDEX | PSoC | Next RX slot the PSoC fills. 0..7 |
| 0xBE8 | RX_READ_INDEX | Host | Next RX slot the host reads. 0..7 |
| 0xBEC | TX_WRITE_INDEX | Host | Next TX slot the host fills. 0..7 |
| 0xBF0 | TX_READ_INDEX | PSoC | Next TX slot the PSoC consumes. 0..7 |

RX = PSoC to host. TX = host to PSoC.

### 2.6 Remote I2C data window

| Offset | Size | Notes |
|--------|------|-------|
| 0x3C00 | 1024 bytes | Data window for remote I2C reads and writes |

---

## 3. Audio data path

### 3.1 Sample format

The HAL plugin reports one physical format per stream:

- `mFormatID = 'lpcm'`
- `mFormatFlags = 0x0C` (`kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked`)
- `mBitsPerChannel = 32`
- `mBytesPerFrame = channels * 4`, `mFramesPerPacket = 1`

The HAL copies samples with `memcpy`. No conversion happens. The DMA ring
therefore holds native-endian, 32-bit signed integer, frame-interleaved
samples.

### 3.2 Ring layout

Each direction has one ring of 0x4000 frames. Each frame holds all device
channels for that direction, 4 bytes each.

    byte offset(frame f, channel c) = (f * channels + c) * 4
    ring bytes = 0x4000 * channels * 4

Ensemble: playback ring = 16384 * 36 * 4 = 2,359,296 bytes. Record ring =
16384 * 34 * 4 = 2,228,224 bytes.

The FPGA gets the ring IOVA and `*_AUDIO_BUFFER_SIZE = channels * 0x4000`.
The unit is frames times channels, not bytes.

The HAL writes a cycle at `sampleTime mod 0x4000`. If the cycle crosses the
end, it splits the copy in two (`_writePlaybackData`, `_readRecordingData`).

### 3.3 Timestamps

The kext allocates one shared page (memory type 2). Layout:

    struct ApogeeTimeStamp {
        uint64_t sampleTime;   // frames, advances by 0x4000 per interrupt
        uint64_t hostTime;     // clock_get_uptime() at the interrupt
    };

The MSI filter routine reads no status register. It does
`sampleTime += 0x4000; hostTime = clock_get_uptime();` and returns false.
The FPGA raises one MSI per ring wrap. There is no other interrupt source.

The HAL `getZeroTimeStamp` reads both fields twice until they are stable,
then returns them. The seed increments on each `startIO`, modulo 100.

`setHardwareRunningState` zeroes the page unless the device is on its way
back from sleep.

### 3.4 DMA burst depth (SAMPLEDEPTH)

`Ensemble2AudioSystem::_getSampleDepthGivenSampleRate`:

| Sample rate | Depth |
|-------------|-------|
| <= 48000 | 2 |
| <= 96000 | 8 |
| > 96000 | 32 |

`startHardware(depth)` writes `SAMPLEDEPTH = depth - 1`. The init path
writes 0x1F (depth 32). Values above 64 are rejected.

### 3.4.1 Latency and safety offset

The HAL plugin reports these values in frames. The IO buffer size does not
change them. The stream latency is 0 in both directions
(`_streamGetPropertyData` @0x4623d).

| Sample rate | Safety offset | Device latency in | Device latency out |
|-------------|---------------|-------------------|--------------------|
| <= 48000 | 3 | 13 (2 + 11) | 43 (2 + 41) |
| <= 96000 | 12 | 19 (8 + 11) | 22 (8 + 14) |
| > 96000 | 48 | 45 (32 + 13) | 43 (32 + 11) |

- The safety offset is the same for input and output
  (`Ensemble2AudioSystem::_getSafetyOffset` @0x45a2e).
- The device latency is the burst depth plus a unit term
  (`_getLatencyOffset` @0x459c6,
  `Ensemble2AudioDevice::_getUnitSpecificLatencyOffset` @0x95dc8). The
  unit term is probably the converter delay.
- The input latency also adds an "extra ADC delay" per rate. It aligns
  several units to the slowest one (`adjustForMaxSystemDelay` @0x61892)
  and is 0 for one unit. The plugin sends it as command 0x2D,
  `ExtraADCDelay`, 6 bytes.
- No FPGA register feeds a latency value.

### 3.5 Start and stop

`startHardware(depth)` (via command gate):

1. Reject if the "needs hotplug" flag is set.
2. Write `SAMPLEDEPTH`.
3. `setHardwareRunningState(true)`:
   - Zero playback and record rings.
   - `requireMaxBusStall(10000)` (10 us).
   - `_startDMA(3, true)`.
   - `INTERRUPT bit 24 = timestampEnabled`.
   - Zero the timestamp page.

`stopHardware`:

1. Zero both rings.
2. `requireMaxBusStall(0)`.
3. `IOSleep(50)`.
4. `_startDMA(3, false)`.
5. Clear `INTERRUPT` bit 24.

The HAL calls `startHardware` from `Ensemble2AudioSystem::startIO` after it
enables timestamps on the first unit and computes the depth.

### 3.6 Sample rate

The sample rate is a PSoC setting, not an FPGA register. Command 0x29 with a
1-byte `SampleRateIndex`:

| Index | Rate |
|-------|------|
| 0 | 44100 |
| 1 | 48000 |
| 2 | 88200 |
| 3 | 96000 |
| 4 | 176400 |
| 5 | 192000 |
| 7 | invalid |

The channel count does not change with sample rate in this driver.

---

## 4. DMA buffers

### 4.1 Allocation

`_allocateDMAMemoryBuffers(type, bytes)`:

1. `IOBufferMemoryDescriptor::withOptions(options, bytes, 1)`.
2. `IODMACommand::withSpecification(kIODMACommandOutputHost64, 64, 0,
   kMapped, 0, 0x1000, IOMapper::copyMapperForDevice(pci), NULL)`.
3. `setMemoryDescriptor`, `genIOVMSegments` with one segment.
4. Write the segment address to the type's LOW/HIGH registers.

One segment is required. The alignment is 4096.

| Memory type | Buffer | Options | Bytes |
|-------------|--------|---------|-------|
| 0 | Playback ring | 0x10012 = KernelUserShared, PhysicallyContiguous, DirectionOut | outCh * 0x4000 * 4 |
| 1 | Record ring | 0x10011 = KernelUserShared, PhysicallyContiguous, DirectionIn | inCh * 0x4000 * 4 |
| 2 | Timestamp page | 0x10001 = KernelUserShared, DirectionIn | 8 requested, 16 used |
| 3 | Meter buffer | 0x10011 | 2 * numHostMeters + 4 |

The timestamp page has no IODMACommand. Only the CPU writes it.

### 4.2 Failure text

On allocation failure the kext logs
`Ensemble Thunderbolt FATAL COULD NOT ALLOC <PLAYBACK|RECORD|METER> BUFFER,
PLEASE REBOOT YOUR MAC`. Contiguous allocations of 2.3 MB can fail on a
fragmented system. A new driver must handle this.

### 4.3 Re-registration

`_refreshFPGAAudioRegisters` and `_attachDriverToTheUnit` rewrite all
address and size registers. The kext calls them after wake, after a PSoC
restart, and on the "attach" misc request.

`_detachDriverFromTheUnit` stops meter DMA, stops audio, and zeroes all six
address registers. It sets the "needs hotplug" flag.

### 4.4 Meter DMA

The FPGA writes meter values into the meter buffer on a timer.

    METER_TIMER = (K / rateHz) - 1
    K = 0x3B9AC (244140) if GENERAL bit 30 set, else 0x1DCD6 (122070)

The kext uses 20 Hz. Meter DMA runs whenever a user client is attached,
independent of audio.

Buffer layout (`Ensemble2AudioDevice::CopyMeterData`):

| Offset | Size | Content |
|--------|------|---------|
| 0x00 | 1 | Sequence counter. The FPGA changes it on every update |
| 0x01 | 3 | Padding |
| 0x04 | 30 * 2 | Input meters, uint16, one per input channel |
| 0x40 | 30 * 2 | Output meters, uint16 |
| 0x7C | 4 * 2 | Headphone 1 L/R, Headphone 2 L/R (measured by routing a tone to destinations 15 and 16) |
| 0x84 | 16 * 2 | Playback 1-16, before the mixers (measured with a tone per playback channel) |
| 0xA4 | 8 * 2 | Mixer master outputs, 4 stereo mixers |
| 0xB4 | n * 2 | DSP core meters, present if `numHostMeters > 88`. The Ensemble FPGA reports 88 (8.6) |

Ensemble reports 88 host meters, so the buffer is 4 + 88 * 2 = 0xB4
bytes. The HAL thread polls byte 0 every 5 ms and copies the block when the
value changes.

Each value is a linear peak level with full scale at 16384 (2^14): a
1 kHz sine at -40 dBFS reads 164, and at -20 dBFS reads 1639. So
dBFS = 20 * log10(value / 16384). The meters measure before the monitor
mute. Measured with the open driver.

The HAL does not interpret the values. It repacks them into an
`ApogeeMeterData` struct for Apogee Control (`_serializeMeterData`). The
struct header holds four uint16 counts. The Ensemble constructor writes
`0x0008_0024_0010_001E`: 30 inputs, 16 in group 2, 36 outputs, 8 mixer
masters. Element writes 16 and 10 for the fixed groups, so group 4 is one
stereo pair per mixer (Ensemble 4 mixers, Element 4 mixers plus FX send).

`Ensemble2AudioDevice::CopyMeterData` fills the 36-entry output group in
this order:

| Position | Source | Content |
|----------|--------|---------|
| 0, 1 | 0x40, 0x44, or 0x48 | Monitor L/R. Copy of the output pair of the active speaker set |
| 2 to 5 | 0x7C | Four output meters that precede the physical outputs |
| 6 to 35 | 0x40 | 30 physical outputs |

The names of positions 2 to 5 and of group 2 live in Apogee Control, not in
the driver. The driver treats them as opaque.

---

## 5. PSoC control protocol

### 5.1 Command packet (HAL to kext)

`_Ensemble2DriverCommandPacket`, 120 bytes (0x78):

| Offset | Size | Field |
|--------|------|-------|
| 0 | 8 | Header. The HAL writes the 64-bit value 1 |
| 8 | 1 | Message type (5.2) |
| 9 | 1 | Command ID (5.6) |
| 10 | 1 | Param 1 (channel, output, mixer index) |
| 11 | 1 | Param 2 |
| 12 | 1 | Data length |
| 13 | 107 | Data |

The kext copies the packet into a wire message and queues it. The 10 ms
timer drains up to 8 queued messages per tick.

### 5.2 Message types

| Type | Name | Wire size | Wire layout after the 8-byte header |
|------|------|-----------|-------------------------------------|
| 1 | Set, 1 byte | 12 | type, cmd, p1, data[0] |
| 2 | Set, block | roundup4(13 + len) | type, cmd, p1, p2, len, data[0..len) |
| 3 | Get | 12 | type, cmd, p1, p2 |
| 4 | Get all | 12 | type, 0, 0, 0 |
| 5 | PSoC restarted | kext to HAL only | len = 0 |

Wire size counts the header. The maximum is 29 words (116 bytes).

### 5.3 Slot ring (host to PSoC)

`_sendCommandMessage(words, count)`:

1. Read `TX_WRITE_INDEX (0xBEC)` and `TX_READ_INDEX (0xBF0)`. Both must be
   <= 8.
2. If `(write + 1) & 7 == read`, the ring is full. Retry once, then return
   false. The message stays queued.
3. Write the words to `0x800 + write * 0x78`.
4. Write TX state `[write] = (1 << 5) | count`.
5. Write `TX_WRITE_INDEX = (write + 1) & 7`.
6. Set `GENERAL` bit 6 (doorbell).

`_actualInitializeMessageBuffer`:

1. Write TX state 0..7 = 0.
2. Write 0xBEC, 0xBF0, 0xBE4, 0xBE8, 0x7E0, 0xBE0 = 0.
3. Drop every queued message.
4. Set `GENERAL` bit 5.

### 5.4 Slot ring (PSoC to host)

`_readCommandMessage`, called from the timer after the TX drain:

1. Read `RX_WRITE_INDEX (0xBE4)` and `RX_READ_INDEX (0xBE8)`.
2. If equal, nothing is pending.
3. Read RX state `[read]`. Length = bits 4:0 (clamped to 30). Bit 5 must be
   set.
4. Read `length` words from `0x400 + read * 0x78`.
5. Write RX state `[read] = 0`.
6. Write `RX_READ_INDEX = (read + 1) & 7`.

`_processPropertyNotificationFromHardware` parses the words. Words 0 and 1
are a header and are copied into packet offset 0. From word 2, a sequence
of records follows. Each record starts with a type byte:

| Type | Layout | Words |
|------|--------|-------|
| 1 | type, cmd, p1, value | 1 |
| 2 | type, cmd, p1, p2, len, data[len] (len <= 100). The copy ignores the message length | 2 + ceil((len - 3) / 4) |

Each record becomes one 120-byte packet to the HAL. Any other type byte
logs `message error` and stops the parse.

### 5.5 PSoC events (Ensemble only)

`Ensemble2Device::_checkDeviceExtraInterruptStatus` runs at the top of each
timer tick. It reads `PSOC_EVENT (0x7E0)`:

| Value | Action |
|-------|--------|
| 0xFFFFFFFF | Device is gone. Drop the queue, return false |
| 0 | Nothing |
| bit 1 | Write `HANDSHAKE (0xBE0) = 0xABCD1234` |
| bit 0 | PSoC restarted: clear sneaky flag, reinit slots, send type-5 packet, `_refreshFPGAAudioRegisters`, restart meter DMA |

After a nonzero read the kext writes `0x7E0 = 0`. Element models return true
without any register access.

### 5.6 Command IDs

From `Ensemble2Command::*` and `ApogeeTBTCommand::*` in the HAL plugin.
"p1" and "p2" are packet offsets 10 and 11. "data" starts at offset 13.

A type-1 command with one argument sends it in `data[0]` with `p1 = 0`
(`_sendCommand(cmd, value)`). For such a command, the p1 column below names
the value in `data[0]`. A command with two arguments sends `p1` and
`data[0]` (`_sendCommand(cmd, p1, value)`).

| ID | Name | Type | p1 | p2 / data |
|----|------|------|----|-----------|
| 0x01 | AnalogInputType | 1 | channel (0..11) | type. Analog 1-4: +4dBu, -10dBV, Mic, Instrument. Analog 5-8: no Instrument. Front Mic: Mic only. Guitar 1-2: Instrument only |
| 0x02 | MicGain | 1 | channel 0-7, 8 = Front Mic | dB, 1 per step. 0-75, Front Mic 0-40 (`_setGainForChannel` @0x8e7e6) |
| 0x03 | InstrumentGain | 1 | channel 0-3, 10-11 = Guitar 1-2 | dB, 1 per step. 0-65, Guitar 0-45 |
| 0x04 | SoftLimit | 1 | channel | mode |
| 0x05 | PhantomPower | 1 | channel | bool |
| 0x06 | PhaseInverse | 1 | channel | bool |
| 0x07 | GroupID (input pair link) | 1 | channel 0-7, 10-11 | 0 = off, pair index + 1 = linked. The vendor writes both channels of the pair (`AEgp` setter @0x90e91) |
| 0x08 | HighPassFilter | 1 | channel | bool |
| 0x09 | InputRouting (record pair routing) | 1 | record pair (0..16) | source code (5.9). The vendor HAL never sends it |
| 0x0A | InsertEnable | 1 | 0 = Analog 1, 1 = Analog 2 | bool |
| 0x0D | AnalogOutputReferenceLevel | 1 | channel | level |
| 0x0E | AnalogOutputTrim | 1 | channel | trim |
| 0x0F | MainOutputMode | 1 | mode | |
| 0x10 | ActiveSpeakerSet | 1 | bitmask: 1 = A, 2 = B, 4 = C | |
| 0x11 | OutputAttenuation | 1 | monitor output | attenuation, 0 to 64 |
| 0x12 | OutputMute | 1 | monitor output | bool |
| 0x13 | OutputDim | 1 | monitor output | bool |
| 0x14 | OutputSumToMono | 1 | monitor output | bool |
| 0x15 | OutputRouting / OutputPairRouting | 1 | destination | source |
| 0x16 | FrontGuitarOutputMode | 1 | channel | 0 = Thru, 1 = From Software |
| 0x19 | TalkbackMicOn | 1 | bool | |
| 0x1A | OpticalPortFormat | 1 | port | format |
| 0x1C | FrontGuitarOutputAttenuation | 1 | channel | value |
| 0x1D | FrontGuitarMatchUnityGainMode | 1 | channel | bool |
| 0x1E | InputChannelPairAllocation | 1 | count (1..255) | |
| 0x1F | OutputChannelPairAllocation | 1 | count (1..255) | |
| 0x20 | KeyboardVolumeControl | 1 | monitor output | |
| 0x21 | MeterPeakHold | 1 | 0 Off, 1 2 seconds, 2 Infinite | |
| 0x22 | MeterOverHold | 1 | 0 Off, 1 2 seconds, 2 Infinite | |
| 0x23 | ActiveEncoderSelect | 1 | 0..11, not 8 or 9 | |
| 0x24 | LockHomeScreen | 1 | bool | |
| 0x25 | TouchPadAssignment | 1 | pad (0..3) | function |
| 0x26 | PeripheralPrefix | 1 | char | |
| 0x27 | Identify | 1 | bool | |
| 0x28 | ClearMeters | 1 | 1 | |
| 0x29 | SampleRate | 1 | SampleRateIndex | |
| 0x2A | ClockSource | 1 | source | |
| 0x2B | WordClockInputTermination | 1 | bool | |
| 0x2C | ResetRouting | 1 | bool | |
| 0x2D | ExtraADCDelay | 2 | | 6 bytes |
| 0x32 | MixerChannelFaderLevel | 2 | channel | p2 = mixer, 2 bytes |
| 0x33 | MixerChannelPan | 2 | channel | p2 = mixer, 1 byte |
| 0x34 | MixerChannelSolo | 2 | channel | p2 = 0, 1 byte |
| 0x35 | MixerChannelMute | 2 | channel | p2 = mixer, 1 byte |
| 0x38 | MixerChannelIsVisible | 2 | channel | p2 = mixer, 1 byte. Gates the channel into that mixer: a hidden channel is not mixed. The report is type 1, one value per channel, 1 if any mixer has the channel visible. The vendor writes all mixers |
| 0x39 | MixerChannelIsStereo | 2 | channel | p2 = mixer, 1 byte. A write to the even channel of a pair flags both channels. A write to the odd channel flags only itself. The report is type 1, one per channel, 1 if any mixer has the flag. The vendor writes the even channel in all mixers, then copies level, mute, solo, visibility, and solo safe to the partner (`Ensemble2MixerMatrix::_setMixerChannelIsStereo` @0x3421c). `Ensemble2Command::setMixerChannelIsStereo` @0x128c refuses channels 8 and 9. The PSoC then sets the pan of both channels to 64 in all mixers (0x168AA) |
| 0x3A | MixerChannelSoloSafe | 2 | channel | 1 byte |
| 0x50 | FunctionalTestMode | 1 | mode | |
| 0x51 | FunctionalTestResetAll | 1 | 0xAB | |
| 0x60 | FirmwareUpdateDFUMode | 1 | firmware type | |
| 0x61 | FirmwareUpdateComplete | 1 | firmware type | 1 |
| 0x62 | FirmwareUpdatePacket | 2 | | packet bytes |
| 0x63 | RestartPSocFirmware | 1 | reset type | |
| 0x66 | MultiUnitSettings | 2 | | 2 bytes |
| 0x90 | MixerIsPreFader | 2 | mixer 0-3, p2 0 | 1 byte. Reported as type 1. Mixers 2-4 tap their inputs before (1) or after (0) the Mixer 1 faders |
| 0x91 | DAWMixerFaderLevel | 2 | channel (0..29) | p2 = DAW mixer, 2 bytes big-endian |
| 0x92 | DAWMixerPan | 2 | channel (0..29) | p2 = DAW mixer, 1 byte |
| 0x93 | DAWMixerMute | 2 | channel (0..29) | p2 = DAW mixer, 1 byte (inverted) |
| 0x94 | DAWMixerRouting | 1 | bool | 0x80 |
| 0xA0 | OpticalIsSubMix | 1 | bool | 1 only with a second linked unit |
| 0xD0 | DSPCoreWriteCode | 2 | words in this chunk, 1 to 23 | p2 = start address. data = first-chunk flag, last-chunk flag, thread, total words, then the words |
| 0xD1 | DSPCoreWriteCoefficients | 2 | as 0xD0 | as 0xD0 |
| 0xD3 | DSPCoreRouting | 2 | input index in record order (5.11) | p2 = 0. data = DSP input channel, DSP output channel, mode. Mode bit 0 sends the DSP output to the mixers. Bits 0 and 1 together also send it to the record channel (8.6). The Ensemble HAL sends mode 0 or 1, with the same channel twice |
| 0xD4 | DSPCoreWriteStateInit | 2 | as 0xD0 | as 0xD0. Replaces all 256 state words of the thread (8.2) |
| 0xD6 | DSPCoreErase | 2 | memory: 0 code, 1 coefficients, 2 state | p2 = start address. data = 1, 1, thread, word count |
| 0xD7 | DSPCoreHaltResume | 2 | 0 halt, 1 resume | Halt: p2 = start address, data = 0, 0, thread, word count. Resume clears every halt and ignores the other bytes |

Section 8 describes the DSP core and its commands 0xD0 to 0xD7.

Mixer channels are 0 to 47. Channels 0 to 29 follow the input meter
order, 30 to 45 carry Playback 1 to 16, and 46 and 47 are the mixer
master L and R. The vendor HAL never writes channel 9, the second half of
the front panel mic. Measured with a tone per playback channel and the
mixer meters:

- `MixerChannelFaderLevel` is 2 bytes, big-endian, 0.1 dB per step.
  600 is 0 dB and 720 is +12 dB, the unit's maximum. The vendor HAL never
  sends more than 660 (+6 dB). 0 closes the channel.
- `MixerChannelPan` is 0 to 127, center 64. It works as balance: the near
  side stays at 0 dB. A mono input (Analog 1 in Mixer 1) follows a pan law
  instead: 64 gives 0.704 (-3.0 dB) on each side, 0 gives 1.000 left and
  0.0003 right, and 127 gives 1.000 right and 0.018 left.
- `MixerChannelSolo` and `MixerChannelSoloSafe` exist on Mixer 1 only.
  Solo arrives as type 1 without a mixer index.

DAW fader level: `uint16 = (clamp(dB) + offset) * scale`, byte-swapped.
The constants are in the HAL at `setDAWMixerFaderLevel`, unverified here.

#### PSoC handlers

Source: the PSoC firmware (`scripts/psoc-firmware.py`). Addresses in this
part are PSoC flash addresses. "FPGA a" is the FPGA byte address on the
PSoC bus (5.13). "Matrix d ← s" is a routing matrix entry (5.10).

The host parser (0x153F8) builds one message per record. The handlers read
p1 at message offset 9, p2 at offset 10, and data from offset 11. A type-1
record puts its value in data[0] and sets p2 = 0. So every command accepts
type 1 and type 2 alike. For a type-2 record with len > 99, the parser
copies no data, calls the dispatcher, and stops.

The dispatcher (0x16228) switches on the command byte. Each message has a
source:

| Source | Origin |
|--------|--------|
| 0 | Front panel and firmware events, through 0x16FBC |
| 1 | Host |
| 2 | Replay of the saved settings at power-up (0x20B78 reads the EEPROM at 0x4000_8000, 0x20D18 replays it) |

The PSoC keeps a settings table (`0x21738`): 60 entries of command, value
size, p1 count, p2 count, default, and a volatile flag. Its initializer is at
flash 0x25EBC (RAM 0x1FFF_8BEC). After a handler, the dispatcher copies data
into the table (0x20918), unless the handler stored the value itself or the
source is 2. The table has entries for 0x01 to 0x0A, 0x0D to 0x16, 0x19,
0x1A, 0x1C, 0x1D, 0x20 to 0x29, 0x2A, 0x2B, 0x2D, 0x32 to 0x35, 0x38 to
0x3A, 0x40, 0x42, 0x43, 0x52, 0x53, 0x61, 0x64, 0x66, 0x90 to 0x94, 0xA0,
0xD2, and 0xD5.

- A change from source 0 marks a report (5.7). A host write does not.
- A change from source 0 or 1 starts an EEPROM save, except for volatile
  entries and for 0x23. Volatile: 0x19, 0x27, 0x28, 0x2D, 0x40, 0x42, 0x43,
  0x52, 0x53, 0x61, 0x64, 0x66, 0x91 to 0x94, 0xD2, 0xD5.
- At power-up, the PSoC replays each saved setting through the dispatcher.
  So 0x09 and 0x15 routes survive a power cycle. 0xD3 routes do not.
- The display code (0x19738) also acts on 0x0F, 0x10, 0x12 to 0x14, 0x19,
  0x21 to 0x23, 0x25, 0x28 to 0x2A, 0x50, 0x51, 0x60, 0x63, and 0x64, for
  sources 1 and 2.

| ID | Handler | Checks | Action and hardware |
|----|---------|--------|---------------------|
| 0x01 | 0x14810 | p1 ≤ 7, else only stored | Sets the preamp path over SPI (0x108BC). FPGA 0x0B bit p1 = type is not +4dBu. FPGA 0x08 bit p1 (p1 ≤ 3) = Instrument. FPGA 0x0A bit 4 = any phantom power on. A type change from source 0 or 1 also sets 0x07 of p1 to 0 |
| 0x02 | 0x17368 | p1 ≤ 7: gain ≤ 75. p1 8: gain ≤ 40 | Analog 1-8: preamp SPI, if the type is Mic. Front Mic: I2C device 0x18 (0x12F44). In a group (0x07), the PSoC applies the same change to each channel of the group (0x17020) |
| 0x03 | 0x172EC | p1 ≤ 3: gain ≤ 65. p1 10, 11: gain ≤ 45 | Analog 1-4: preamp SPI, if the type is Instrument. Guitar 1-2: a 3-byte I2C write (0x126D4). Groups as 0x02 |
| 0x04 | 0x1463C | p1 ≤ 7 | FPGA 0x0D bit p1 |
| 0x05 | 0x14698 | p1 ≤ 7 | Preamp SPI. FPGA 0x0A bit 4 = any channel has phantom power and type Mic |
| 0x06 | 0x145E0 | p1 ≤ 7 | FPGA 0x07 bit p1 |
| 0x07 | 0x161DC | none | Also stores the value for the partner channel p1 XOR 1. No hardware access |
| 0x08 | 0x1478C | p1 ≤ 7 | Preamp SPI, if the type is Mic or Instrument |
| 0x09 | 0x14058 | p1 ≤ 16. No check on data[0] | Matrix 0x30 + 2 p1 + i ← data[0] + i, for i = 0, 1. Pair 15 always gets 0x60 (Mixer 1) and pair 16 always 0x66 (FX Send) |
| 0x0A | 0x16C2E | p1 ≤ 1 | FPGA 0x08 bit 6 (Analog 1) or bit 7 (Analog 2) |
| 0x0D | 0x14B48 | p1 ≤ 9 | p1 0, 1: FPGA 0x08 bit 4, 5. p1 2 to 9: FPGA 0x0C bit p1 − 2. 1 = -10dBV |
| 0x0E | 0x14D28 | p1 ≤ 9. Value clamped to 120 | value / 5 goes to an I2C volume chip (0x1138C). value mod 5 goes to FPGA 0x8B + p1 |
| 0x0F | 0x13B90, 0x14C80 | none | Stores the mode, applies the routes of destinations 0 to 3 again, and sets the volume chips |
| 0x10 | 0x13BDC | none | Stores the mask and applies the speaker routes again. An inactive set gets matrix control 0x18 (5.10) |
| 0x11 | 0x14B98 | Value clamped to 64. No check on p1 | I2C volume chips. Steps of the chips: 2 × attenuation, + 30 for dim, 255 for mute (0x14DF8) |
| 0x12, 0x13 | 0x14BD8, 0x14C2C | No check on p1 | as 0x11. A p1 above 2 writes past the RAM table at 0x1FFF_910C |
| 0x14 | 0x13C48 | p1 ≤ 2 | Applies the routes of the monitor output again, through the mono summer (5.10) |
| 0x15 | 0x13DFC | p1 ≤ 16. No check on data[0] | Writes the matrix (5.10) |
| 0x16 | 0x16D1E | none | FPGA 0x09 bit 0 (p1 0) or bit 1 (p1 ≠ 0) = value is 0 (Thru) |
| 0x1A | 0x11D24 | none | FPGA 0x28: port 0 bits 0 and 2, port ≠ 0 bits 1 and 3, set for value 1 (S/PDIF) |
| 0x1C | 0x14EF8 | p1 ≤ 1 | I2C volume chip, if 0x1D of p1 is 0 |
| 0x1D | 0x14EF8 | p1 ≤ 1 | On: the guitar output attenuation follows the 0x03 gain of channel 10 + p1. Off: it takes the 0x1C value |
| 0x27 | 0x16EB6 | none | Starts or stops a display timer. No FPGA access |
| 0x29 | 0x1455C | index > 5 gives 44.1 kHz | Index 0 to 5: 44.1, 48, 88.2, 96, 176.4, 192 kHz (0x21670). FPGA 0x0E = rate code (5.13), FPGA 0x37 = ADC delay, converter set-up over I2C (0x10490). With an external clock, report 0x42 = 0 |
| 0x2A | 0x1459C | none | FPGA 0x0F = value. Value 0 also sets reports 0x42 = 1 and 0x64 = 1. Other values set both to 0 |
| 0x2B | 0x16EF8 | none | FPGA 0x09 bit 2 = value is 0 |
| 0x2C | 0x139C8, 0x13AE0 | none | data[0] = 0: resets the output routes (5.10). data[0] ≠ 0: resets the record routes |
| 0x2D | 0x153A4 | none | Stores 6 delay bytes, one per rate. FPGA 0x37 ← the byte of the current rate. 88.2 and 96 kHz both use byte 3 |
| 0x32 | 0x17854 | none | Mixer gain of p1 in mixer p2 (FPGA 0x1000, 5.13). A stereo even channel also sets p1 + 1 |
| 0x33, 0x35 | 0x179EC, 0x177E8 | none | as 0x32 |
| 0x34, 0x3A | 0x17930, 0x178E4 | none | Solo and solo safe. They change the gains of all mixers |
| 0x38 | 0x167BC | none | Hidden (0) also clears 0x34 and 0x3A of p1 |
| 0x39 | 0x168AA | p1 even | A change sets the flag of p1 + 1 and the pan of both channels to 64 in all 4 mixers. It also copies 0x38, 0x3A, 0x34, and the 0x35 and 0x32 of each mixer to p1 + 1 (0x15E18) |
| 0x51 | 0x16F1A | data[0] = 0xAB | Resets all settings to their defaults (0x205CC) and saves them |
| 0x60 to 0x63 | 0x17FB4, 0x18198, 0x18098, 0x18344 | | Firmware update and deferred power-state request. 0x60 mode 0 requests CPU reset into the bootloader. 0x63 data 1 sets power state 5, not a direct CPU reset. See [update and recovery boundaries](docs/firmware/psoc-update.md) |
| 0x66 | 0x16722 | none | data[0] = 0 clears 0x34 of channel 46. data[0] and data[1] ≠ 0: output routes of destinations 0 to 6, 15, and 16 replace codes 0x60 to 0x67 with 0x10 to 0x17 |
| 0x90 | 0x16AB4 | p1 = 0 ignored | Recomputes the mixer gains on a change |
| 0x91 to 0x93 | 0x18638 | none | DAW mixer p2, channel p1. FPGA 0x1400 + 0x100 p2 (5.13) |
| 0x94 | 0x140C0, 0x187EC | data[0] = 0 means 0x80 | DAW mixer p1 passes playback code data[0] at unity. Output routes that use that playback code switch to DAW mixer output 0x68 + 2 p1 |
| 0xD0 to 0xD7 | 0x13574 to 0x1421C | none | Section 8.6 |

The dispatcher has no case for 0x0B, 0x0C, 0x17 to 0x19, 0x1B, 0x1E to
0x26, 0x28, 0x50, 0x64, 0xA0, 0xD2, and 0xD5. The PSoC only stores these
values, if the settings table has them. It ignores 0x1E and 0x1F.

### 5.7 Reports from the PSoC

`Ensemble2AudioDevice::packetFromHardwareArrived` switches on the command
ID. Report IDs 0x01 to 0x2A echo the setter IDs above with the current
value. Extra report IDs:

| ID | Meaning |
|----|---------|
| 0x40 | Versions, matching `ElementsUpdateVersionInfo.plist`: p1 0 = PSoC firmware (1.5.3), p1 1 = FPGA firmware (0.56), p1 2 = hardware revision (3), p1 3 = front-panel resources (0.6) |
| 0x41 | 8-byte unit ID. The PSoC sends 7 of the 8 bytes |
| 0x42 | External clock lock. data[0] != 0 = locked |
| 0x43 | Power switch on. The HAL then requests all properties |
| 0x44 | Get-all complete. data[0] = 1 |
| 0x52, 0x53 | Functional test result (not decoded) |
| 0x64 | PLL clock lock |
| 0xD2 | DSP core version, 7 bytes |
| 0xD5 | DSP cycle count per thread and sample, data[0]. See 8.1 |

With Word Clock selected and no signal, the unit reports 0x42 = 0 and
0x64 = 0, and the audio DMA stops. With Internal, both report 1.

A Get-all request (type 4) returns one report per property.

The PSoC does not echo a set command. A front-panel change, for example
the volume encoder, produces a report. A host that sends a set command
must update its own copy of the state.

#### PSoC side

Source: the PSoC firmware. The PSoC sends the stored value of a setting
(5.6) as a report. The record is type 1 if the value is 1 byte and the
setting has no p2. Else it is type 2 with p2 and len = value size
(0x15A10).

The report table holds 28 IDs (0x21854, initializer at flash 0x2609C):
0x01 to 0x08, 0x0A, 0x10 to 0x14, 0x16, 0x19, 0x27 to 0x29, 0x40, 0x42,
0x43, 0x52, 0x53, 0x61, 0x64, 0xD2, and 0xD5. Each ID has a bit mask of
pending p1 values. The sender (0x2153C) sends each pending value with
p2 = 0.

- Get (type 3, 0x208E0) marks (command, p1) as pending. The PSoC ignores
  p2, and a Get of an ID that is not in the report table.
- A change from source 0 (5.6) marks a report only for these 28 IDs. So a
  front-panel change of a route or a mixer value sends no report.
- Get-all (type 4 with bytes 1 to 3 zero) makes 0x15668 send, in order:
  0x40 with p1 0 to 3, 0xD2, and 0x41 (0x15C50). Then each setting that
  is not volatile, for each p1 and p2. Then 0x44 as type 2 with data =
  1 and a RAM byte (0x1FFF_9148, meaning unverified). Last, it marks 0x42
  and 0x64 as pending.
- Get-all covers 0x01 to 0x0A, 0x0D to 0x16, 0x1A, 0x1C, 0x1D, 0x20 to
  0x26, 0x29 to 0x2B, 0x32 to 0x35, 0x38 to 0x3A, 0x90, and 0xA0.

The main loop (0x15F58) makes these reports without a request:

| ID | Value | Source |
|----|-------|--------|
| 0x64 | 1 if FPGA 0x02 bit 6 is 0 | 0x16026, only with an external clock source |
| 0x42 | 1 if 0x64 is 1 and the measured rate (FPGA 0x18) is within 5 % of the set rate | 0x16072, only with an external clock source |
| 0xD5 | FPGA 0x180E, when it changes | 0x16118 |
| 0x43 | 1 when the PSoC enters its run state. The front-panel code also sets 0 or 1 through 0x16FBC | 0x15FDE |

### 5.8 Enum values

From the name tables in `Ensemble2AudioDevice::_customPropertyGetPropertyData`
and `getClockSourceNameForID`.

`_Ensemble2ClockSource` (command 0x2A). The second column is the CoreAudio
clock source item ID that the HAL publishes.

| Value | HAL ID | Name |
|-------|--------|------|
| 0 | 0xAF00 | Internal |
| 1 | 0xAF01 | Word Clock |
| 2 | 0xAF002 | SPDIF Coax |
| 3 | 0xAF003 | Optical 1 (name depends on the port format) |
| 4 | 0xAF004 | Optical 2 |

Report 0x42 gives the external clock lock. `data[0] != 0` = locked.

`_Ensemble2AnalogInputType` (command 0x01). The wire value differs from the
ID that the HAL publishes to Apogee Control (`AErl`, `AErN`):

| Wire value | Published ID | Name |
|------------|--------------|------|
| 0 | 0 | +4dBu |
| 1 | 1 | -10dBV |
| 2 | 3 | Mic |
| 3 | 4 | Instrument |

The HAL stores the wire value per input (array at device + 0x2FC, 10
entries). `packetFromHardwareArrived` compares that array against 2 for mic
gain reports and against 3 for instrument gain reports.

`_Ensemble2AnalogOutputReferenceLevel` (command 0x0D, p1 = output 0 to 9):
0 = +4dBu, 1 = -10dBV. The HAL stores it at device + 0x3F8 and publishes
it through the same `AErl` selector with output scope.

`_Ensemble2SoftLimit` (command 0x04, p1 = input 0 to 11): 0 = Off,
1 = On. Ensemble has no soft limit level. The `AEll` and `AElr` selectors
exist only in `ElementAudioDevice`.

`_Ensemble2MonitorOutput` (commands 0x11 to 0x14, 0x20):

| Value | Name |
|-------|------|
| 0 | Headphone 1 |
| 1 | Headphone 2 |
| 2 | Speaker |

`_Ensemble2MainOutChannelModes` (command 0x0F):

| Value | Name |
|-------|------|
| 0 | Line |
| 1 | Stereo |
| 2 | 2 Speaker Sets |
| 3 | 3 Speaker Sets |
| 4 | 5.1 (Out 1-6) |
| 5 | 7.1 (Out 1-8) |
| 6 | 9.1 (Out 1-10) |

`_OpticalPortFormat` (command 0x1A): 0 = ADAT/SMUX, 1 = S/PDIF.

`_Ensemble2Group` (command 0x07): 0 = Off, 1 to 5 = group number.

`_Ensemble2TouchButtonFunction` (host remote-button enum, not command 0x25):

Command 0x25 uses local pad values 0–22 at PSoC `0x1A1B0`.
See the [local pad actions](docs/firmware/front-panel.md#pad-assignments).
The table below describes the separate host enum.

| Value | Name | Value | Name |
|-------|------|-------|------|
| 0 | None | 20 | Polarity |
| 1 | Toggle Device | 21 | Group |
| 2 | Mute Panic | 22 | Soft Limit |
| 3 | Mute Speakers | 23 to 30 | Select Input 1 to 8 |
| 4 | Mute Headphones | 31 | Launch Apogee Control |
| 5 | Mute All Outputs | 32 | Digital Reference Level |
| 6 | Mute Toggle Headphone/Speaker | 33 | High Pass Filter |
| 7 | Dim Speakers | 34 | Insert |
| 8 | Dim Headphones | 35 | Toggle Main Source |
| 9 | Dim All Outputs | 36 to 38 | Select Speaker Set 1 to 3 |
| 10 | Mono Speakers | | |
| 11 | Mono Headphones | | |
| 12 | Mono All Outputs | | |
| 13 | Toggle Speaker Sets | | |
| 14 | Set Main Out to Reference Level | | |
| 15 | Clear Meters | | |
| 16 | Toggle Talkback | | |
| 17 | Momentary Talkback | | |
| 18 | Analog Input Level | | |
| 19 | 48V Phantom Power | | |

### 5.9 Output routing source codes

Command 0x15 sets `p1 = destination` and `data[0] = source code`. Command
0x09 uses the same codes for the 17 record channel pairs, but the vendor
HAL never sends 0x09 (`Ensemble2Command::setInputRouting` is empty).
Source codes (`Ensemble2AudioDevice::convertToOutputRouteSource`):

| Code | Source |
|------|--------|
| 0x00, 0x02, 0x04, 0x06 | Analog 1-2, 3-4, 5-6, 7-8 |
| 0x08 | Front Panel Mic |
| 0x0A | Guitar 1-2 |
| 0x10 to 0x1E, even | Optical 1-2 to 15-16 |
| 0x30 to 0x52, even | Playback 1-2 to 35-36 |
| 0x54 | S/PDIF Coax in |
| 0x60, 0x62, 0x64, 0x66 | Mixer 1, Mixer 2, Mixer 3, FX Send |

The Ensemble has 4 mixers (`getNumberOfMixers` returns 4). The vendor
preset routes Mixer 1 to Line 1-2 and Mixers 2 and 3 to the headphones.

Destinations: `d` = 0 to 14 drives output pair `2d, 2d+1` of Line 1-10,
Guitar Out 1-2, S/PDIF Coax, Optical 1-16. 15 and 16 are Headphone 1 and 2.
A tone routed to each destination lit exactly that output meter pair, and
15 and 16 lit the meter group at 0x7C. In "2 Speaker Sets" mode, set A
plays the route of destination 0 and set B the route of destination 1. The
inactive set stays silent. The vendor HAL writes the speaker source to
destinations 0 and 1, and to 2 in "3 Speaker Sets" mode, so all sets play
the same source.

The HAL publishes the 36 output channels as "Playback 1" to "Playback 36".
The DMA output ring therefore carries software playback channels, not
physical outputs. The PSoC routing matrix assigns each playback pair to a
physical destination.

### 5.10 Routing matrix

Source: the PSoC firmware. The FPGA routing matrix has 256 destinations.
Each destination takes one source. The PSoC writes the source of
destination d to FPGA 0x0200 + d and a control byte to FPGA 0x0300 + d
(5.13). The control byte is 8 for each route. Outputs of an inactive speaker
set get 0x18. The meaning of the control bits is unverified. Source numbers
are the codes of 5.9.

| Source | Signal | Evidence |
|--------|--------|----------|
| 0x00 to 0x07 | Analog 1-8 | Input table at RAM 0x1FFF_8290 (0x140E8) |
| 0x08, 0x09 | Front panel mic | as above |
| 0x0A, 0x0B | Guitar 1-2 | as above |
| 0x10 to 0x1F | Optical 1-16 | as above |
| 0x20 + k | Mono sum of monitor bus k, the same value on L and R | 0x13DFC |
| 0x30 to 0x53 | Playback 1-36 | 5.9 |
| 0x54, 0x55 | S/PDIF coax in | Input table |
| 0x60 to 0x67 | Mixer 1 L/R, Mixer 2, Mixer 3, FX Send | 5.9 |
| 0x68 + 2m, 0x69 + 2m | DAW mixer m (0 to 3), L/R | 0x13DA4 |
| 0x70 to 0x7F | DSP outputs 0 to 15 | 0x14188, 8.6 |
| 0x90 to 0xAF | Unknown. Start-up routes them to destinations 0xE0 to 0xFF | 0x13860 |

| Destination | Signal | Written by |
|-------------|--------|------------|
| 0x00 to 0x09 | Line out 1-10 | 0x15 with p1 0 to 4. Table at RAM 0x1FFF_829C maps p1 to the destination |
| 0x0A, 0x0B | Guitar out 1-2 | 0x15 with p1 5 |
| 0x0C, 0x0D | Headphone 1 | 0x15 with p1 15 |
| 0x0E, 0x0F | Headphone 2 | 0x15 with p1 16 |
| 0x10 to 0x1F | Optical out 1-16 | 0x15 with p1 7 to 14 |
| 0x20 + 2k, 0x21 + 2k | Mono summer input of monitor bus k. k 0 to 2 = speaker destinations 0 to 2, k 3 and 4 = Headphone 1 and 2 | 0x15, if 0x14 is on |
| 0x30 to 0x51 | Record channel r = d − 0x30 (5.11) | 0x09, 0xD3 |
| 0x52, 0x53 | S/PDIF coax out | 0x15 with p1 6 |
| 0x60 to 0x7D | Mixer feed and host input meter of input r = d − 0x60 | 0xD3, start-up (0x13860) |
| 0x80 to 0x8F | Playback 1-16. Probably the mixer channels 30 to 45 (inferred) | 0x2C, start-up |
| 0x90 to 0x99 | Front-panel input meters 0 to 9: Analog 1-8, Guitar 1-2 (inferred) | Start-up (0x14020) |
| 0x9A to 0xA9 | Front-panel output meters 10 to 25: Line out 1-10, Guitar out 1-2, Headphone 1 and 2 (inferred) | 0x15 (0x13D10) |
| 0xB0 to 0xB7 | Unknown. 0x2C routes the mixer outputs 0x60 to 0x67 to them | 0x2C |
| 0xC0 to 0xCF | DSP inputs 0 to 15 | 0xD3 |
| 0xE0 to 0xFF | Unknown. Start-up routes sources 0x90 to 0xAF to them | Start-up |

The meter rows are inferred from counts: the display code reads 10 input
meters and 16 output meters from FPGA 0x0040 (0x19208). The source of each
front-panel meter is the source of its input or output.

0x15 (0x13DFC) writes these entries for p1 = d and code c:

1. With 0x66 data[0] and data[1] not 0, and d ≤ 6 or d ≥ 15, codes
   0x60 to 0x67 become 0x10 to 0x17.
2. If DAW mixer m passes playback code c (0x94), c becomes 0x68 + 2m.
3. The output pair o comes from the table at RAM 0x1FFF_829C. The meter
   pair is 0x9A + 2d for d ≤ 5, 0xA6 for d 15, and 0xA8 for d 16.
4. If monitor bus k of d sums to mono (0x14), the matrix gets 0x20 + 2k
   + i ← c + i. The output and meter entries get 0x20 + k. Else the
   matrix gets o + i ← c + i and meter + i ← c + i.
5. In "2 Speaker Sets" and "3 Speaker Sets" modes, a speaker destination
   that is not in the 0x10 mask gets control byte 0x18.

The matrix commands check few arguments:

- 0x15 and 0x09 accept any source code. So 0x15 with code 0x70 + o sends
  DSP outputs o and o + 1 to an output pair. 0x09 with 0x70 + o records
  them. Not tested on the unit.
- 0xD3 checks nothing and computes each index modulo 256 (8.6). It is the
  only command that writes destinations 0xC0 to 0xCF.
- No command writes destinations 0x80 to 0x8F, 0xB0 to 0xB7, or 0xE0 to
  0xFF with a host-chosen source.

Default routes:

- 0x2C with data[0] = 0 uses the table at RAM 0x1FFF_8280. Playback 1-12
  go to Line out 1-10 and Guitar out. Playback 13-14 go to S/PDIF, 15-30
  to Optical, and 1-2 to both headphones. It also sets 0xB0 + i ← 0x60 + i
  and 0x80 + i ← 0x30 + i.
- 0x2C with data[0] ≠ 0 uses the table at RAM 0x1FFF_8268. Each input goes
  to its record pair. Mixer 1 goes to record pair 15, FX Send to pair 16.
- Start-up (0x13860) sets 0x60 + r ← input r and the input meter taps. It
  also sets 0x80 + i ← 0x30 + i and 0xE0 + i ← 0x90 + i.

### 5.11 Input channel order (Ensemble)

From `Ensemble2AudioDevice::createChannelName(isInput = true, index)`:

| Index | Name |
|-------|------|
| 0 to 7 | Analog 1 to 8 (prefix shows Mic, Line, or Instrument) |
| 8, 9 | Front Panel Mic (two channels, same name) |
| 10, 11 | Guitar 1, 2 |
| 12, 13 | SPDIF Cx L, R |
| 14 to 29 | Optical 1 to 16 |
| 30 to 33 | Mix 1 L, Mix 1 R, FX Send L, FX Send R |

The index tests in `createChannelName` are `<= 7`, `<= 9`, `<= 11`,
`<= 13`, `<= 29`. Indices above 29 use `index - 34 + 4` to select the
mixer return name.

The record ring holds 34 channels in this order. Channels 30 and 31 carry
Mixer 1. With Analog 1 in Mixer 2, 3, or 4 only, channels 30 to 33 stayed
silent.

### 5.12 Custom CoreAudio properties (Apogee Control API)

Apogee Control and Maestro talk to the HAL plugin through custom
`AudioObjectPropertySelector` codes. A replacement plugin must answer the
same selectors to keep those apps. The plugin's own debug names follow.
All names carry the prefix `kApogeeCustomProperty_`.

| Selector | Name | Selector | Name |
|----------|------|----------|------|
| `AA2o` | AnalogInToOpticalOut | `AEon` | MonitorOutputNameForID |
| `ADbg` | Debug | `AEor` | OutputLevelRange |
| `AEC1` | MiscChannelProperty1 | `AEos` | MonitorOutputIDList |
| `AEC2` | SpecialEnsembleChannel | `AEpc` | PeakMeterClear |
| `AEC3` | IsAnalog | `AEph` | PhantomPower |
| `AEDs` | MiscDeviceSettings | `AEpx` | Prefix |
| `AEE2` | LockHomeView | `AErI` | OutputSourceIDList |
| `AEFT` | FunctionalTest | `AErM` | AnalogIOTypeIDList |
| `AEFU` | FirmwareUpdate | `AErN` | AnalogIOTypeNameForID |
| `AEGE` | GUIComponentDisable | `AErO` | OutputSourceID |
| `AEGi` | FPButtonFunctionID | `AErb` | RemoteButtonAssignment |
| `AEGl` | FPButtonFunctionIDList | `AErc` | RemoteAssignment |
| `AEGn` | FPButtonFunctionNameForID | `AEre` | PhaseInverse |
| `AEL8` | TouchFunction | `AErl` | AnalogIOTypeID |
| `AEMI` | MixerID | `AEsl` | SoftLimitID |
| `AEML` | MixerChannelLabel | `AEt1` | VersionInfo |
| `AEMR` | MixerChannelLevelRange | `AEt2` | ResetRouting |
| `AEMl` | MixerChannelLevel | `AEtr` | TrimValue |
| `AEMm` | MixerChannelMute | `AEtv` | TrimValueRange |
| `AEMp` | MixerChannelPan | `APDU` | DeviceUID |
| `AEMs` | MixerChannelSolo | `APG0` | AutoLaunchMaestro |
| `AERN` | OutputSourceNameForID | `APG4` | EnablePopup |
| `AESd` | SnapshotDirty | `APOW` | OwnedObjects |
| `AESs` | Snapshot | `APOw` | DeviceList |
| `AEac` | AutoLaunchElementControl | `APen` | ElementName |
| `AEbb` | Identify | `AUna` | UnitName |
| `AEdS` | DigitalReferenceLevelIDList | `Adlg` | DialogBox |
| `AEdT` | DigitalReferenceLevelNameForID | `Afln` | UnitOffline |
| `AEdr` | DigitalReferenceLevelID | `Amdi` | MasterDeviceID |
| `AEf1` | OpticalFormatID | `Amdl` | MasterDeviceIDList |
| `AEf2` | OpticalFormatIDs | `Amid` | ModuleIndex |
| `AEf3` | OpticalFormatNameForID | `Amni` | MasterDeviceNameForID |
| `AEgQ` | GroupIDList | `Amtp` | ModuleType |
| `AEgR` | GroupNameForID | `Atcf` | TalkbackConfiguration |
| `AEgi` | RemoteButtonFunctionID | `Atdi` | TalkbackDestinationID |
| `AEgl` | RemoteButtonFunctionIDList | `Atdl` | TalkbackDestinationIDList |
| `AEgn` | RemoteButtonFunctionNameForID | `Atdn` | TalkbackDestinationNameForID |
| `AEgp` | GroupID | `Atsi` | TalkbackSourceID |
| `AEgr` | InputGainRange | `Atsl` | TalkbackSourceIDList |
| `AEhf` | HighPassFilter | `Atsn` | TalkbackSourceNameForID |
| `AEie` | InsertEnableForID | `DSP0` | DSPConfiguration |
| `AEir` | InsertEnable | `DSP1` | DSPParameterAndEditorChanges |
| `AEit` | InsertID | `DSP2` | DSPCoreMeters |
| `AEiu` | InsertIDList | `DSP3` | DSPRackIsBypassed |
| `AEiv` | InsertNameForID | `DSP4` | DSPRackIsLinked |
| `AEl3` | OutputLevel | `DSP5` | DSPGlobalLinkEnable |
| `AEll` | SoftLimitLevel | `DSP6` | DSPCoefficientChanges |
| `AElr` | SoftLimitLevelRange | `DSP7` | DSPPrograms |
| `AEm1` | OutputMute | `DSP8` | DSPMonitor |
| `AEm4` | OutputDim | | |
| `AEm5` | OutputSumToMono | | |
| `AEmD` | MeterData | | |
| `AEmI` | MixerIDList | | |
| `AEmg` | InputGain | | |
| `AEmo` | MonitorOutputID | | |
| `AEoc` | OverMeterClear | | |
| `AEof` | OpticalFormat | | |
| `AEog` | OutputSettingID | | |
| `AEoh` | OutputSettingIDList | | |
| `AEoj` | OutputSettingNameForID | | |

Property data travels as CFPropertyList-encoded CFData
(`_readDataFromCFPropertyList`, `_writeDataToCFPropertyList`). Values are
32-bit integers or CFStrings. The apps also read plain properties such as
`kAudioDevicePropertyClockSource` with the IDs in section 5.8.

### 5.13 FPGA registers on the PSoC bus

Source: the PSoC firmware. The PSoC reaches the FPGA through its External
Memory Interface, 8 bits wide: FPGA byte address a is PSoC address
0x6080_0000 + a. The PSoC keeps a RAM copy of the control registers 0x08
to 0x0D (0x1190C) and writes the whole byte on each change. Multi-byte
values are little-endian. "Unverified" marks a meaning that the code does
not settle.

| Address | Access | Function | PSoC code |
|---------|--------|----------|-----------|
| 0x0000 | R | 0xAB when the FPGA is ready. The PSoC polls it at start-up | 0x11754 |
| 0x0002 | R | Status. Bit 6 = PLL not locked (report 0x64). Bits 5:3 + 1 = hardware revision (report 0x40, p1 2). The event handler reads bit 0 | 0x11B4C, 0x1FD84 |
| 0x0003 | W | 0xA2 after the PSoC writes host messages. Likely the host doorbell, unverified | 0x11D98 |
| 0x0004 | R | Read once at start-up. A nonzero value changes the start state. Meaning unknown | 0x17540 |
| 0x0005, 0x0006 | R | FPGA firmware version for report 0x40, p1 1 | 0x17404 |
| 0x0007 | W | Bit n: phase invert on Analog n + 1 | 0x11C98 |
| 0x0008 | W | Bits 3:0: Instrument on Analog 1-4. Bits 5:4: -10dBV on Line out 1-2. Bits 7:6: insert on Analog 1-2 | 0x1190C |
| 0x0009 | W | Bits 1:0: guitar out Thru. Bit 2: word clock termination off. Bit 3: set by the guitar gain code, meaning unknown. Bits 7:6: sample-rate set-up | 0x1190C |
| 0x000A | W | Bits 3:2: sample-rate set-up. Bit 4: phantom power supply | 0x1190C |
| 0x000B | W | Bit n: Analog n + 1 is not +4dBu | 0x1198C |
| 0x000C | W | Bit n: Line out n + 3 is -10dBV | 0x11A10 |
| 0x000D | W | Bit n: soft limit on Analog n + 1 | 0x11A94 |
| 0x000E | W | Sample rate: 0 = 44.1, 1 = 48, 2 = 88.2, 3 = 96, 4 = 176.4, 5 = 192 kHz | 0x11860 |
| 0x000F | W | Clock source, the 0x2A value (5.8) | 0x118E4 |
| 0x0011 to 0x0018 | R | Unit ID for report 0x41, read from 0x0018 down to 0x0011. The overlap with 0x0018 is unexplained | 0x11B74 |
| 0x0018 to 0x001B | R | 32-bit period count of the external clock. The PSoC converts it to a sample rate | 0x12150 |
| 0x001C, 0x0020, 0x0024 | R, RW, W | Event flags, event enable, and event clear, bits 0 to 5. Meaning of the bits unverified | 0x116F8, 0x1167C, 0x11614 |
| 0x0028 | W | Optical port format, 2 bits per port (5.6, 0x1A) | 0x11D24 |
| 0x002D | W | 1 after start-up, 0 before a firmware update. Meaning unverified | 0x1F8FC, 0x17FB4 |
| 0x002E to 0x0034 | RW | Flash writes for the firmware update | 0x12334 to 0x12570 |
| 0x0035 | R | The start-up code reads bit 1 after 0x0000 reads 0xAB | 0x11754 |
| 0x0037 | W | ADC delay of the current sample rate (0x2D) | 0x153A4 |
| 0x0040 + 2m | R | Front-panel meter m, 16 bits. m 0 to 9: inputs. m 10 to 25: outputs. Bit 15: over | 0x19208 |
| 0x0080 | W | 3 resets the front-panel meter state, unverified | 0x12130 |
| 0x008B + n | W | Fine trim of Line out n + 1, 0 to 4 steps (0x0E) | 0x14D28 |
| 0x0200 + d | W | Routing matrix: source of destination d (5.10) | 0x11C24 |
| 0x0300 + d | W | Routing matrix: control byte of destination d | 0x11C5C |
| 0x0400 to 0x0BF3 | RW | Message slots and indices, the same bytes as BAR0 0x400 to 0xBF3 (2.5) | 0x11DB0 to 0x11F68 |
| 0x0C00 | RW | Data buffer of the firmware update | 0x12444 |
| 0x1000 + 0x100 m + 0x80 s + 2c | W | 16-bit gain of channel c (0 to 63) into side s (0 L, 1 R) of mixer m. m 0 to 3: Mixer 1 to 4. m 4 to 7: DAW mixers 1 to 4. The gain format is in 0x18534 | 0x11BE4 |
| 0x1800 to 0x27FF | | DSP core (8.6) | |

---

## 6. User client interface

Class `com_apogeedigital_ElemEnsUserClient`. The HAL opens it with
`IOServiceOpen(service, task, 0)`. The kext accepts a second client. The
newest client replaces the device's client. On client close or death the
kext stops the hardware and disables meter DMA.

### 6.1 External methods

| Index | Name | Input | Output |
|-------|------|-------|--------|
| 0 | Open | none | none |
| 1 | Close | none | none |
| 2 | StartHardware | struct: uint32 depth (nonzero) | none |
| 3 | StopHardware | none | none |
| 4 | SendRequest | struct: 120-byte packet | none |
| 5 | MiscRequest | struct: uint32 type, uint32 arg, data | struct: words |
| 6 | AccessBAR0Register | struct: uint32 op, uint32 offset, uint32 value | struct: uint32 |

`AccessBAR0Register` op 0 = write, op 1 = read. No offset check exists.

The HAL retries any `IOConnectCallMethod` failure up to 9999 times. On
`kIOReturnNoResources` (0xE00002D5, queue full) it sleeps 200 us between
tries.

### 6.2 MiscRequest types

| Type | Name | arg / data | Output |
|------|------|------------|--------|
| 0 | EnableRemoteI2C | arg = bool | |
| 1 | ReadRemoteI2C | arg = bytes | bytes (max 1024) |
| 2 | WriteRemoteI2C | arg = bytes, data follows | |
| 3 | PSoCBootloaderStatus | | uint32: 1, 2, or 0 |
| 4 | AttachDetach | arg = 1 detach, else attach | |
| 5 | ResetMessageBuffer | | |
| 6 | EnableTimeStamp | arg = bool | |
| 7 | SetSneaky | arg = bool | |
| 8 | KextVersion | | uint32 0x0807 (bytes: major, minor, patch) |
| 9 | MultiUnitSyncStatus | | uint32 MUSYNC_CSR |
| 10 | MultiUnitSyncControl | arg = pause count (byte) | |
| 11 | OverUnderFlowStatus | | uint32 reg 0x5C, then cleared |
| 12 | DebugPrintRegisters | | (IOLog) |
| 13 | ReadBAR0Block | | N words from offset 0 |
| 14 | SymphonyAIM | | uint32 reg 0x84 bits 7:0 |
| 15 | FPGASneakyBit | | uint32 reg 0x84 bit 31 |

### 6.3 Shared memory

`clientMemoryForType(type)` returns the buffer for memory types 0 to 3
(section 4.1). The HAL maps them with `IOConnectMapMemory64`.

### 6.4 Notifications

`registerNotificationPort` stores the port. Each PSoC record goes out as a
Mach message: `msgh_bits = 0x13` (copy send), `msgh_id = 0`, kernel size
0x98 = 32-byte header + 120-byte packet.

### 6.5 Power management

Three power states, registered with `registerPowerDriver`:

| State | Caps | Kext action in `setPowerState` |
|-------|------|--------------------------------|
| 0 | 0 | Same as state 1 |
| 1 | 0x1000 (low power) | Stop meter DMA, drain queue, cancel timer, remember run state, stop hardware |
| 2 | 0x8002 (usable, on) | Rewrite FPGA registers, resume queue, restart meter DMA and timer, zero rings, restart hardware if it was on |

---

## 7. Remote I2C engine

Register `I2C_CTRL (0x18)` and window `0x3C00`.

Enable: write `0x18 = 0x00040000`, then `0x18 = 0x006C0036`. Disable: write
`0x18 = 0`. The meaning of 0x6C and 0x36 is unverified. 0x36 is likely the
I2C address byte.

Transfer (`_performRemoteI2CTransfer(isWrite, bytes)`):

1. For a write, copy the data into `0x3C00` as 32-bit words.
2. `ctrl = (ctrl & 0xBFFFFF7F) | (bytes << 8) | ((!isWrite) << 7) | 0x40000000`.
   Bit 30 = start. Bit 7 = read. Bits 15:8 = byte count.
3. `IOSleep((9 * bytes + 9) / 150)` (x86_64 `0x5FF6`, integer division).
4. Poll bit 31 (busy) at 1 ms until clear. Give up after 999 tries.
5. For a read, copy the words out of `0x3C00`.

Maximum transfer is 1024 bytes.
The helper logs a timeout, but the miscellaneous request still returns success.
The read helper also copies the buffer after timeout.
See the [independent transport review](docs/firmware/verify-update-transport.md).

---

## 8. DSP core

The FPGA contains a programmable DSP core. The Apogee FX Rack plugins can
run on it. The HAL plugin holds the FX programs, links them into the core
memory, and sends them with commands 0xD0 to 0xD7 (5.6). The unit answers
a Get-all with one 0xD2 version report.

Source: the arm64 slice of the HAL plugin, and tests on the unit (8.7).
Addresses in this section are arm64 addresses. `scripts/dsp-programs.cpp`
prints the FX programs.

Terms:

- **Thread**: one of the 16 instruction streams of the core.
- **Fragment**: a part of an FX program that runs in one thread.
- **Option**: one way to split an FX program into fragments.
- **Rack**: the FX chain on one channel (`DSPChannelRack`).
- **Biquad**: a second-order IIR filter section.

### 8.1 Resources

| Resource | Value | Source |
|----------|-------|--------|
| Threads | 16 | `DSPCoreMemoryBlock` rejects thread 0x10 and higher. `Ensemble2Command::DSPCoreEraseAll` erases threads 0 to 15 |
| Memories | Code (0), coefficients (1), state (2), per thread | Memory argument of 0xD6 |
| Memory size | 256 words of 32 bits, per memory and thread | `DSPCoreMemoryBlock` rejects offsets 0x100 and higher |
| DSP I/O channels | 16 | `DSPCoreResourceManager` allocates channels 0 to 15. The instruction fields are 6 bits. In the FPGA routing matrix, DSP input n is destination 0xC0 + n and DSP output n is source 0x70 + n (8.6) |
| Racks | 30, one per input in record order (5.11) | `Ensemble2AudioDevice::DSPCoreNumberOfHardwareInputs` |
| Cycle budget | `floor(125e6 / (16 * fs))` per thread and sample: 177 at 44.1 kHz, 162 at 48 kHz, 81 at 96 kHz | `DSPController::estimatedDSPCycleCount` @0x62238. The unit reports 162 at 48 kHz |

Report 0xD5 replaces the estimate.
`Ensemble2AudioDevice::packetFromHardwareArrived` passes its `data[0]` to
`DSPController::setDSPCycleCount`. On report 0x43 (power on), the same
function requests 0xD5, sends a Get-all, and erases all threads (@0x81d44).

All threads share one state address space. A store or copy instruction
(8.3) carries a 12-bit state address: the thread in bits 17:14 and the
offset in bits 13:6.

### 8.2 Load sequence

`FXFragment::load` @0x25a98 loads one fragment:

1. Relocate the code (8.3).
2. Allocate the code, coefficient, and state blocks in the HAL memory map.
3. Halt the code range in the thread (0xD7, p1 = 0).
4. Write the code (0xD0).
5. Write the initial state (0xD4), if the fragment has state.
6. Write the coefficients (0xD1).

`FXFragment::load` sends no resume. `FXProcessor::load` sends it after it
loads all fragments of an FX: `FXFragment::resumeAll` calls the device
resume-all (vtable slot 0x28). `FXFragment::unload` halts the code range,
erases it with 0xD6, and releases the three blocks.

Each transfer goes out in chunks of at most 23 words. A coefficient change
sends only the words from the first to the last changed coefficient
(`FXFragment::setCoefficients` @0x2611c).

Coefficients go on the wire as IEEE 754 single-precision bit patterns.
`FXFragment::setCoefficients` passes its `float` array to 0xD1 without
conversion.

A 0xD4 write goes through a 256-word staging buffer in the FPGA (8.6). The
PSoC puts word i of the transfer at staging word i. After the last chunk,
the FPGA copies the whole staging buffer into the state memory of the
thread, rotated by the start address: `state[(start + j) mod 256] =
staging[j]`. It ignores the count. So every 0xD4 write replaces all state
words of the thread. A 255-word write from address 0 sets words 0 to 254
as given. To change one word, write all 255 words again. The HAL writes
only the zero-filled block of a new fragment, which must also overwrite the
state of other fragments in the same thread. That last point follows from
the rule and is not tested.

### 8.3 Instruction word

Each instruction is one 32-bit word, and bits 5:0 hold the opcode. A thread
runs one instruction per cycle from code address 0. Instructions past the
cycle budget do not run. Coefficient and state words are IEEE 754
single-precision floats. The core has two result registers, r and x.

The HAL relocation functions (`TransformInPlace_*`, @0x94084 to @0x943f8)
give the address fields. The tests on the unit (8.7) give the other fields
and the opcodes. `scripts/dsp/isa.py` repeats the tests.

Arithmetic instructions, opcodes 0x04 to 0x0A, 0x0C to 0x13, and 0x26 to
0x2B:

| Bits | Field |
|------|-------|
| 13:6 | Operand A: coefficient address or state offset |
| 21:14 | Operand B: state offset |
| 23:22 | A select: 0 coefficient, 1 state, 2 r, 3 x |
| 25:24 | B select: 0 zero, 1 state, 2 r, 3 x |
| 27:26 | k. A state operand, A or B, is a circular group of 2^k words |
| 30 | Destination: 1 r, 0 x |
| 31 | Also writes the result to offset 0 of the operand B group |

The linker relocates one state offset per instruction: operand A if its
select is 1, else operand B. A circular group advances one word per
sample, so offset j reads the value that offset 0 held j samples earlier.
k = 0 is a fixed word. The state block of a fragment must align to 2^k
words for its largest k (`FXFragment::sizeMaxStateMode` @0x256e4 returns
`1 << mode`).

| Opcode | Result |
|--------|--------|
| 0x04 | Previous result + A × B. Tested with destination r (ModernEQ) |
| 0x05 | A × B |
| 0x06 | A + B |
| 0x07 | A − B |
| 0x08 | B − A |
| 0x12 | \|A\| |
| 0x26 | max(A, B) |
| 0x27 | min(A, B) |
| 0x28 | max(\|A\|, \|B\|) |
| 0x29 | min(\|A\|, \|B\|) |
| 0x13 | \|B\| |
| 0x2A | A |
| 0x0C, then 0x0E | e^A |
| 0x0F, then 0x11 | ln A |
| 0x09, then 0x2B | B / A |
| 0x0A, then 0x2B | A / B |

Both instructions of a pair take the same operands, as in the vendor
programs. The first one leaves r and x unchanged. A second stage (0x0E,
0x11, or 0x2B) uses the operands of the instruction just before it. Any
instruction can come first, and the first stage only selects the operand.
For A = 0.5 and B = b, the previous instruction gives these results
(`isa.py units`):

| Previous instruction | 0x0E | 0x11 | 0x2B |
|----------------------|------|------|------|
| 0x0C | e^A | ln B | A / B |
| 0x0F | e^B | ln A | A / B |
| 0x09 | e^B | ln B | B / A |
| 0x06, 0x0A, 0x0D, 0x10 | e^B | ln B | A / B |
| 0x07 | e^−B | ln −B | −A / B |
| 0x08 | e^B | ln B | −A / B |

So 0x0D and 0x10 give the same results as any instruction with the same B.
In the opcode map, they are the B forms of 0x0C and 0x0F, as 0x0A is the B
form of 0x09. This is an inference. With one more instruction between the
two stages, the second stage used the operands of that instruction. The
earlier statement that a second stage alone acts on the product A × B came
from a previous instruction with A = 1. The vendor programs do not use
0x13, 0x29, or 0x2A.

The pairs match the latencies of the Altera floating-point IP cores
(UG-01058). With 16 threads, each instruction of a thread has 16 clocks.
Single-precision ALTFP_MULT (5 to 11 clocks), ALTFP_ADD_SUB (7 to 14), and
ALTFP_COMPARE (1 to 3) fit in one instruction. ALTFP_EXP (17), ALTFP_INV
(20), and ALTFP_LOG (21, natural logarithm) do not, so they take two. The
divisions then multiply by an inverse. This is an inference.

Other instructions:

| Opcode | Bits | Meaning |
|--------|------|---------|
| 0x01 | 13:6 | Jump to this address + the offset, a signed 8-bit value. Offset 2 skips one instruction, and 0xFE jumps two back |
| 0x01 | 16:14 | 2 to 5: jump if x meets the condition. 0, 1, 6, and 7: always jump |
| 0x01 | 23:21 | Condition on x, see below |
| 0x02 | 13:6, 17:14, 20:18 | Store: state offset, thread, address mode |
| 0x02 | 21 | Source: 0 r, 1 x |
| 0x02 | 22, 28:23 | Bit 22 also sends the value to an audio output. Bits 28:23 hold the DSP I/O channel |
| 0x0B | 11:6 | Read audio input: DSP I/O channel. The sample goes to r |
| 0x0B | 28:21 | State offset. In ModernEQ (bit 30 set) the sample also goes there |
| 0x14 | 13:6, 17:14, 20:18, 28:21 | Copy a state word: source offset, source thread, address mode, destination offset. Mode m makes the source a circular group of 2^m words. Modes 0 to 3 gave periods of 1, 2, 4, and 8 samples. The destination stays fixed |
| 0x14 | 31:29 | Changed nothing, with sources in thread 0 and thread 1 |
| 0x16 | 13:6, 17:14, 28:21 | As 0x14, and also loads the value into x. Bits 31:29 changed nothing |
| 0x15 | 13:6, 17:14, 20:18, 28:21 | As 0x14, and also loads the value into r. The linker writes 0x15 over an 0x0B when the input comes from another fragment |
| 0x17 | 13:6 | STALL until cycle n. The next instruction runs at cycle n + 1. The linker adds the code start to n and replaces a STALL at the end of a fragment with 0 |

Jump conditions, bits 23:21 of 0x01:

| Bits | Jump when |
|------|-----------|
| 000 | x ≤ 0 |
| 001 | x ≠ 0 |
| 010 | x < 0 |
| 011 | x ≥ 0 |
| 100 | x = 0 |
| 101 | x > 0 |
| 110 | never |
| 111 | always |

The vendor programs set bits 20:17 of 0x01 to 1111, and bits 16:14 to 1,
2, or 3. With bits 16:14 = 2 to 5, the condition tests x. With 0, 1, 6, or
7, the jump always goes to the relative target, even with condition 110
(`isa.py selectors`). The vendor programs use 1 only with condition 111.
Bits 27:24 changed nothing. In the vendor conditional jumps, they hold
values from 0 to 0xD. A value of ±1e-30 counts as nonzero.

Opcodes 0x00, 0x03, 0x18 to 0x25, and 0x2C to 0x3F changed neither r nor
x. The test put them after 0x0D and after 0x10, with destination r and
with destination x (`isa.py unknown`). So none of them gives a square root
or another unit result. 0x38 to 0x3F also left r unchanged with raw
integer words as operand A, so they convert no integers. The large values
of an earlier 0x38 test did not repeat. The vendor programs use none of
these opcodes.

### 8.4 FX programs

The HAL holds six programs as C++ tables (`DSPCore::*FXInfo`). Each table
holds default coefficients for mono and, for ModComp only, for stereo. Each
option lists its fragments. A fragment holds its code, a map from fragment
coefficient slot to FX coefficient index, and "critical sections". In
MonoGain and ModernEQ, the critical sections mark the input read and the
output store.

| Table | HAL name | Product | id | Coefficients, mono and stereo | Words per fragment, per option |
|-------|----------|---------|----|-------------------------------|--------------------------------|
| `noFXInfo` | MonoGain | none | 0 | 4, 0 | 3 |
| `modEQFXInfo` | ModernEQ | ModEQ 6 | 2 | 34, 0 | 34 |
| `eqp1aFXInfo` | TubePultecAuthentic | EQP-1A | 3 | 36, 0 | 48. 24 + 28 |
| `modCompFXInfo` | ModernCompMono | ModComp | 4 | 30, 40 | Mono: 72. 39 + 40. Stereo: 93. 13 + 84. 33 + 47 + 25 |
| `opto3AFXInfo` | VintageCompMono | Opto-3A | 5 | 84, 0 | 190. 64 + 74 + 64. 26 + 50 + 52 + 35 + 38 + 19 |
| `meq5FXInfo` | MEQ5 | MEQ-5 | 8 | 32, 0 | 42. 18 + 28 |

The unsplit Opto-3A program (190 words) exceeds the cycle estimate at
44.1 kHz and higher.

Coefficients 0 to 2 are level slots. `FXProcessor::levelModifiedCoef`
@0x7afc4 multiplies c0 by the rack input level, and c1 and c2 by the rack
output level. In ModernEQ, c1 scales the dry input and c2 scales the EQ
output.

MonoGain:

    0  0000000b  read input, I/O channel 0
    1  42000085  0x05  c2 * r
    2  00400042  0x02  store to state 1 and to audio output 0

ModernEQ is six biquads. Band k (1 to 6) reads its input group x at
state 4k and writes its output group y at state 4k + 4. Each group is a
4-word circular group (bits 27:26 = 2), so offset j holds sample n - j.

     0  4080000b  read input, I/O channel 0, to state 4
     1  490100c5  0x05  c3 * s4     x[n]
     2  49014104  0x04  + c4 * s5   x[n-1]
     3  49018144  0x04  + c5 * s6   x[n-2]
     4  49024184  0x04  + c6 * s9   y[n-1]
     5  c90281c4  0x04  + c7 * s10  y[n-2], bit 31
     6 to 30      bands 2 to 6, the same shape, c8 to c32
    31  42000085  0x05  c2 * r
    32  49010044  0x04  + c1 * s4   dry x[n]
    33  00400002  0x02  store to state 0 and to audio output 0

Band 1 computes `y[n] = c3 x[n] + c4 x[n-1] + c5 x[n-2] + c6 y[n-1] +
c7 y[n-2]`. The feedback terms add, so c6 and c7 hold -a1 and -a2 of the
usual biquad form.

### 8.5 Linker

`DSPCoreLinkSollution` places the fragments of all racks. It tries each
option of each FX in the free code, coefficient, and state blocks.
`canPossiblyBeatBestSollution` drops a branch that cannot beat the best
solution. The log strings compare two solutions on four values:

- samples of delay (`maxSamplesDelay`)
- delay difference between left and right (`lrDelaySkew`)
- threads in use
- average free block size

A split FX passes audio between its fragments through state memory. The
linker clears the audio-output bit of the producer store
(`TransformInPlace_DSPCoreDisableStoreOutput`). It turns the consumer input
read into a copy (0x0B to 0x15). `addFragmentDelayPenalty` charges delay
for each hop. `FXFragment::forbiddenStartAddressRanges` limits the start
address of a fragment. The likely purpose is to keep each copy after the
store that feeds it. This is unverified.

### 8.6 PSoC and FPGA side

The PSoC executes the DSP commands. Its firmware dispatches the command
byte at 0x16256 (`scripts/psoc-firmware.py`) and writes the FPGA through
the External Memory Interface. FPGA byte address a is PSoC address
0x6080_0000 + a. The PSoC writes a 32-bit word as four byte writes, low
byte first (0x12610). Section 5.13 lists the FPGA registers outside the
DSP core.

| FPGA address | Function | PSoC code |
|--------------|----------|-----------|
| 0x0200 + d | Routing matrix: source of destination d. The PSoC also writes 8 to 0x0300 + d | 0x11C24 |
| 0x1800 | Thread for code and coefficient writes | 0x13574 |
| 0x1802 | Enable mask of the 8 halt slots | 0x132DC |
| 0x1805, 0x1806 | Coefficient handshakes: the PSoC writes the thread, then waits for bit 5. 0x1805 comes before the words, 0x1806 after them | 0x136FC, 0x137C8 |
| 0x1807 to 0x180C | DSP core version bytes for report 0xD2 | 0x17404 |
| 0x180E | Cycle count, sent as report 0xD5 | 0x136E4 |
| 0x180F | State copy: write 2 to start it. Bit 0 = busy | 0x135E8 |
| 0x1810, 0x1811, 0x1812 | State copy: thread, start address, count. The FPGA ignores the count (8.2) | 0x135E8 |
| 0x1820 + i, 0x1828 + i, 0x1830 + i | Halt slot i: first address, last address, thread | 0x132DC |
| 0x1C00 + 4a | Code word a of the selected thread | 0x13574 |
| 0x2000 + 4a | Coefficient word a of the selected thread | 0x13754 |
| 0x2400 + 4j | State staging word j | 0x135E8 |

A halt takes a free halt slot. If all 8 slots are in use, the PSoC drops
the halt. A resume clears the mask and so ends every halt.

0xD3 (0x1421C) sets three matrix entries for input r, with DSP input
channel i = data[0], DSP output channel o = data[1], and mode m = data[2].
The input source of r comes from a table (0x140E8).

| Destination | Source |
|-------------|--------|
| 0xC0 + i (DSP input i) | Input r, if m bit 0 is set. Otherwise the PSoC leaves it |
| 0x60 + r (mixer feed of r) | DSP output 0x70 + o, if m bit 0 is set. Otherwise input r |
| 0x30 + r (record channel of r) | DSP output 0x70 + o, if m bits 0 and 1 are set. Otherwise input r |

The PSoC checks none of the four bytes, and it computes each index in 8
bits. DSP input i is destination (data[0] + 0xC0) mod 256. The DSP output
source is (data[1] + 0x70) mod 256. The input source of r is Analog 1
(0x00) for r ≥ 30. The PSoC writes the entries in table order, so a
later entry wins. Thus 0xD3 can put any source s on DSP input n. Send
p1 = 0x60 + n and data = n, (s − 0x70) mod 256, 1:

| Order | Entry |
|-------|-------|
| 1 | 0xC0 + n ← Analog 1 |
| 2 | 0x60 + p1 = 0xC0 + n ← s |
| 3 | 0x30 + p1 = 0x90 + n ← Analog 1. This is front-panel meter tap n (5.10) |

For example, s = 0x60 puts Mixer 1 L on DSP input n, and s = 0x30 puts
Playback 1 there. This follows from the code and is not tested on the
unit. With s = 0x60 and the DSP output in Mixer 1, the signal loops back.
Mode 0 with the same p1 sets DSP input n to Analog 1 again.

Mode 3 is the FX Rack "Print" mode: the record channel carries the FX
output (8.7). The Ensemble HAL sends only mode 0 or 1, and the FX Rack
plugin shows "Print is not available in version ..., please use DualPath
Monitor".

Meters: BAR0 register 0x1C reports 88 meters on this unit (4.4). For an
input with active FX, `ElEnsDSPController::copyMeterData` @0x525b4 shows
the input meter, which taps after the DSP, as the FX output level. It
takes the FX input level from the DSP core meters, at the DSP input
channel of the input. With 88 meters, the buffer holds no DSP core meters.

### 8.7 Tests on the unit

Measured with the open driver at 48 kHz. `scripts/dsp/dsp.py` sends the
commands through `raw.send` of ensemble-control. Each load erased all
threads, followed 8.2 in thread 0 at address 0 with DSP I/O channel 0, and
sent a resume-all. The record stream gave the reference: channel 8 is the
dry front panel mic, and channels 30 and 31 are Mixer 1 (5.11). The
speaker output stayed muted.

- A Get of 0xD5 returns 162.
- 0xD3 with p1 = 0 routes Analog 1, and p1 = 8 routes the front panel
  mic. So p1 is the input index in record order. data[2] = 0 removes the
  route.
- The FX output replaces the input in the input meter and in the mixers.
  The record stream keeps the dry input.
- MonoGain adds 3 samples to the mixer path. For c2 = 0.5, 0.25, -1, and
  0, the gain against the route-off gain is 0.500, 0.250, -1.001, and
  0.000.
- The program `c3 * s4`, then a store, reads 2048 on the input meter for
  c3 = 0.25 and s4 = 0.5. That is 0.125 of full scale (4.4).
- The same program with s4 = 0.5, s5 = 0.25, and zeros up to s11 reads
  s4, s5, s6, s7 in turn for bits 27:26 = 2. Bits 27:26 = 0, 1, and 3
  give a period of 1, 2, and 8 samples.
- With bits 30 and 31 set, `c3 * s4` keeps s4 at 0.5 for c3 = 1. For
  c3 = 0.5, s4 decays to 0.
- The ModernEQ program, with bands 2 to 6 set to pass, gives these
  responses. c3 = 1 passes the input. c4 = 1 delays it by 1 sample, and
  c5 = 1 by 2 samples. c6 = 0.5 gives the impulse response 1, 0.49,
  0.26, 0.11. c7 = 0.5 gives 1.04, -0.03, 0.54, -0.02, 0.28. c1 = 0.5
  with c2 = 0 passes the dry input at 0.5.
- STALL 159 lets two more instructions run, and STALL 160 does not. So
  cycles 0 to 161 run at 48 kHz.
- After full writes of two patterns, one-word 0xD4 writes to s40 and s100
  left s8, s40, s100, and s200 at the values that `state[(start + j) mod
  256] = staging[j]` predicts (`isa.py state`).
- A program that writes 0.25 to DSP output 3, with 0xD3 data = 2, 3, m on
  Analog 1: m = 1 put 0.25 in Mixer 1, m = 3 also on record channel 0,
  and m = 0 and 2 left both dry (`isa.py routes`). MonoGain on the front
  panel mic with m = 3 recorded c2 times the input, 3 samples late.
- A loop with a backward jump (offset 0xFE) ran three times. 0x14 with
  source thread 1 copied a word of thread 1. A state operand A with k = 3
  stepped through its group (`isa.py extra`).
- A second stage used the operands of the instruction just before it, and
  not those of its first stage (`isa.py units`).
- Jump selectors 0, 1, 6, and 7 always jumped to the relative target
  (`isa.py selectors`).
- 0x14 and 0x15 with address mode m read a group of 2^m words, and 0x15
  also loaded r (`isa.py modes`). Bits 31:29 of 0x14 and 0x16 changed
  neither the copy, x, r, nor a word of thread 1 (`isa.py copybits`).
- The opcodes without a known function changed neither r nor x
  (`isa.py unknown`).
- A halted thread sends exact zeros to its DSP I/O channels. Early in the
  tests, a resume-all after a code swap left the thread halted a few
  times, and a second resume-all restarted it. Later, 30 swaps, half of
  them after an erase, never stayed halted.

For the opcode tests, `scripts/dsp/isa.py` sends DSP I/O channel 0 to
Analog 1 and channel 1 to Analog 2. Mixer 1 pans them hard left and hard
right. The left channel carries 0.25 b, where b steps through a circular
group of eight state words. The right channel carries the result. Each
capture gives eight points. Tests with unbounded results limit r to ±10
before the 0.1 scale, so the right channel stays within full scale.

The input meters hold their peaks for 2 s (`meters/peakHold`), so a level
decrease shows late. After the tests, 0xD3 with data[2] = 0 and an erase
of all threads returned the inputs to dry.

### 8.8 Open questions

- Why a resume-all sometimes did not restart the thread. The PSoC has no
  path that drops a resume.
- What bits 27:24 of a conditional jump do. The vendor programs set them,
  but they changed nothing in the tests.
- Whether the opcodes without a known function write state words or DSP
  I/O channels. The tests read only r and x.
- Whether a store (0x02) with address mode m writes a group of 2^m words,
  as 0x14 reads one. This is not tested.
- Whether the FPGA sends DSP core meters when the host asks for more than
  88 meters. The host must then enlarge the meter buffer.
- The Cyclone V image itself. Project Mistral documents the Cyclone V
  bitstream format, which can show how the core is built.

---

## 9. Notes for a new driver

### 9.1 Minimum viable data path

1. Match `IOPCIDevice` with `0x220119C2`. Set `IOPCITunnelCompatible`.
2. Map BAR0. Enable memory and bus master.
3. Allocate two contiguous rings: 36 * 0x4000 * 4 and 34 * 0x4000 * 4 bytes,
   4096-aligned, one IOVA segment each. Allocate one page for timestamps.
4. Write `NUMBER_OF_CHANNELS = (17 << 16) | 18`.
5. Write `INPUT_AUDIO_BUFFER_SIZE = 34 * 0x4000`,
   `OUTPUT_AUDIO_BUFFER_SIZE = 36 * 0x4000`.
6. Write both ring IOVAs to the LOW/HIGH pairs.
7. Write `SAMPLEDEPTH = 1` for 44.1 or 48 kHz.
8. Set `GENERAL |= 0x05A00000`. Set `INTERRUPT |= 0x01000000`.
9. On each MSI: `sampleTime += 0x4000`, `hostTime = now`.
10. Copy 32-bit integer frames at `sampleTime mod 0x4000`.

Without the PSoC protocol the unit keeps its last settings and clock source.
Sample rate changes need command 0x29.

### 9.2 Watch items

- The FPGA never reports a status bit for the MSI. A shared vector cannot
  be disambiguated. Keep one vector.
- Firmware below revision 0x56 refuses DMA. Read PCI config 0x08 first.
- Hot unplug returns 0xFFFFFFFF from `0x7E0`. Every register read returns
  all ones after unplug.
- The kext never touches `HOST_CONTROL`, `STATUS` bits, or the
  `CUR_*_ADDRESS` registers. A new driver can use `CUR_*` for position
  instead of the wrap interrupt. This is unverified.
- The PSoC message slots hold 8 entries. Queue in software when full.

### 9.3 Unverified items

- Bit layouts of `STATUS`, `HOST_CONTROL`, `INTERRUPT` bits 22 and 26.
- Names of meter group 2 (0x84) and output positions 2 to 5 (0x7C). Apogee
  Control assigns them. The driver never reads them.
- The two header words of the PSoC wire messages. The HAL sends 1, the
  PSoC reply header is copied but never read.
- The timer period of 10 ms. The vtable slot matches `setTimeoutUS(10000)`
  with one slot of tolerance.
