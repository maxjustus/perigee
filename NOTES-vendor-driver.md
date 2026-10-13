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
| 0xB4 | n * 2 | DSP core meters, present if `numHostMeters > 88` |

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
| 0x32 | MixerChannelFaderLevel | 2 | mixer | channel, 2 bytes |
| 0x33 | MixerChannelPan | 2 | mixer | channel, 1 byte |
| 0x34 | MixerChannelSolo | 2 | mixer | channel, 1 byte |
| 0x35 | MixerChannelMute | 2 | mixer | channel, 1 byte |
| 0x38 | MixerChannelIsVisible | 2 | channel | p2 = mixer, 1 byte. Gates the channel into that mixer: a hidden channel is not mixed. The report is type 1, one value per channel, 1 if any mixer has the channel visible. The vendor writes all mixers |
| 0x39 | MixerChannelIsStereo | 2 | channel | p2 = mixer, 1 byte. A write to the even channel of a pair flags both channels. A write to the odd channel flags only itself. The report is type 1, one per channel, 1 if any mixer has the flag. The vendor writes the even channel in all mixers, then copies level, mute, solo, visibility, and solo safe to the partner (`Ensemble2MixerMatrix::_setMixerChannelIsStereo` @0x3421c). `Ensemble2Command::setMixerChannelIsStereo` @0x128c refuses channels 8 and 9. The effect on pan is not measured |
| 0x3A | MixerChannelSoloSafe | 2 | channel | 1 byte |
| 0x50 | FunctionalTestMode | 1 | mode | |
| 0x51 | FunctionalTestResetAll | 1 | 0xAB | |
| 0x60 | FirmwareUpdateDFUMode | 1 | firmware type | |
| 0x61 | FirmwareUpdateComplete | 1 | firmware type | 1 |
| 0x62 | FirmwareUpdatePacket | 2 | | packet bytes |
| 0x63 | RestartPSocFirmware | 1 | reset type | |
| 0x66 | MultiUnitSettings | 2 | | 2 bytes |
| 0x90 | MixerIsPreFader | 2 | mixer 0-3, p2 0 | 1 byte. Reported as type 1. Mixers 2-4 tap their inputs before (1) or after (0) the Mixer 1 faders |
| 0x91 | DAWMixerFaderLevel | 2 | mixer | channel, 2 bytes big-endian |
| 0x92 | DAWMixerPan | 2 | mixer | channel, 1 byte |
| 0x93 | DAWMixerMute | 2 | mixer | channel, 1 byte (inverted) |
| 0x94 | DAWMixerRouting | 1 | bool | 0x80 |
| 0xA0 | OpticalIsSubMix | 1 | bool | 1 only with a second linked unit |
| 0xD0 | DSPCoreWriteCode | 2 | words in this chunk, 1 to 23 | p2 = start address. data = first-chunk flag, last-chunk flag, thread, total words, then the words |
| 0xD1 | DSPCoreWriteCoefficients | 2 | as 0xD0 | as 0xD0 |
| 0xD3 | DSPCoreRouting | 2 | input index in record order (5.10) | p2 = 0. data = DSP I/O channel, DSP I/O channel, 1 on or 0 off. The Ensemble HAL sends the same I/O channel twice |
| 0xD4 | DSPCoreWriteStateInit | 2 | as 0xD0 | as 0xD0 |
| 0xD6 | DSPCoreErase | 2 | memory: 0 code, 1 coefficients, 2 state | p2 = start address. data = 1, 1, thread, word count |
| 0xD7 | DSPCoreHaltResume | 2 | 0 halt, 1 resume | p2 = start address. data = 0, 0, thread, word count. Resume-all sends p1 = 1 and all other bytes 0 |

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

With Word Clock selected and no signal, the unit reports 0x42 = 0 and
0x64 = 0, and the audio DMA stops. With Internal, both report 1.
| 0xD2 | DSP core version, 7 bytes |
| 0xD5 | DSP cycle count per thread and sample, data[0]. See 8.1 |

A Get-all request (type 4) returns one report per property.

The PSoC does not echo a set command. A front-panel change, for example
the volume encoder, produces a report. A host that sends a set command
must update its own copy of the state.

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

`_Ensemble2TouchButtonFunction` (command 0x25, remote button assignment):

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

### 5.10 Input channel order (Ensemble)

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

### 5.11 Custom CoreAudio properties (Apogee Control API)

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
3. `IOSleep((9 * bytes + 9) / 1000)`.
4. Poll bit 31 (busy) at 1 ms until clear. Give up after 999 tries.
5. For a read, copy the words out of `0x3C00`.

Maximum transfer is 1024 bytes.

---

## 8. DSP core

The FPGA contains a programmable DSP core. The Apogee FX Rack plugins can
run on it. The HAL plugin holds the FX programs, links them into the core
memory, and sends them with commands 0xD0 to 0xD7 (5.6). The unit answers
a Get-all with one 0xD2 version report.

Source: the arm64 slice of the HAL plugin, and tests on the unit (8.6).
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
| DSP I/O channels | 16 | `DSPCoreResourceManager` allocates channels 0 to 15. The instruction fields are 6 bits |
| Racks | 30, one per input in record order (5.10) | `Ensemble2AudioDevice::DSPCoreNumberOfHardwareInputs` |
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

`FXFragment::load` sends no resume. The caller that resumes the core is
unverified. `FXFragment::unload` halts the code range, erases it with 0xD6,
and releases the three blocks.

Each transfer goes out in chunks of at most 23 words. A coefficient change
sends only the words from the first to the last changed coefficient
(`FXFragment::setCoefficients` @0x2611c).

Coefficients go on the wire as IEEE 754 single-precision bit patterns.
`FXFragment::setCoefficients` passes its `float` array to 0xD1 without
conversion.

Do not use 0xD4 to change single words while a program runs. A one-word
write changed other state words in the thread, also while the thread was
halted (8.6). The HAL uses 0xD4 only to fill the state block of a new
fragment.

### 8.3 Instruction word

Each instruction is one 32-bit word, and bits 5:0 hold the opcode. A thread
runs one instruction per cycle from code address 0. Instructions past the
cycle budget do not run. Coefficient and state words are IEEE 754
single-precision floats. The core has two result registers, r and x.

The HAL relocation functions (`TransformInPlace_*`, @0x94084 to @0x943f8)
give the address fields. The tests on the unit (8.6) give the other fields
and the opcodes. `scripts/dsp/isa.py` repeats the tests.

Arithmetic instructions, opcodes 0x04 to 0x0A, 0x0C to 0x13, and 0x26 to
0x2B:

| Bits | Field |
|------|-------|
| 13:6 | Operand A: coefficient address or state offset |
| 21:14 | Operand B: state offset |
| 23:22 | A select: 0 coefficient, 1 state, 2 r, 3 x |
| 25:24 | B select: 0 zero, 1 state, 2 r, 3 x |
| 27:26 | k. A state operand B is a circular group of 2^k words |
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
| 0x0C, then 0x0E | e^A |
| 0x0F, then 0x11 | ln A |
| 0x09, then 0x2B | B / A |
| 0x0A, then 0x2B | A / B |

Both instructions of a pair take the same operands, as in the vendor
programs. The first one leaves r and x unchanged. 0x0E, 0x11, or 0x2B alone
acts on the product A × B of the previous instruction. After an add with
B = zero, 0x0E gave e^0 = 1.

Other instructions:

| Opcode | Bits | Meaning |
|--------|------|---------|
| 0x01 | 13:6 | Jump to this address + the offset. Offset 2 skips one instruction |
| 0x01 | 23:21 | Condition on x, see below |
| 0x02 | 13:6, 17:14, 20:18 | Store: state offset, thread, address mode |
| 0x02 | 21 | Source: 0 r, 1 x |
| 0x02 | 22, 28:23 | Bit 22 also sends the value to an audio output. Bits 28:23 hold the DSP I/O channel |
| 0x0B | 11:6 | Read audio input: DSP I/O channel. The sample goes to r |
| 0x0B | 28:21 | State offset. In ModernEQ (bit 30 set) the sample also goes there |
| 0x14 | 13:6, 28:21 | Copy a state word: source offset, destination offset |
| 0x16 | 13:6, 28:21 | As 0x14, and also loads the value into x |
| 0x15 | 13:6, 17:14, 20:18, 28:21 | Copy from state: offset, thread, address mode, destination offset. The linker writes 0x15 over an 0x0B when the input comes from another fragment. Not tested |
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
2, or 3. In the tests, words with equal bits 23:21 jumped alike, whatever
bits 16:14 and 27:24 held. A value of ±1e-30 counts as nonzero.

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

### 8.6 Tests on the unit

Measured with the open driver at 48 kHz. `scripts/dsp/dsp.py` sends the
commands through `raw.send` of ensemble-control. Each load erased all
threads, followed 8.2 in thread 0 at address 0 with DSP I/O channel 0, and
sent a resume-all. The record stream gave the reference: channel 8 is the
dry front panel mic, and channels 30 and 31 are Mixer 1 (5.10). The
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
- A one-word 0xD4 write to s40 changed s39, s41, s100, s200, and s254,
  and left s2, s8, and s15. Other one-word writes cleared most of a
  circular group.
- A halted thread sends exact zeros to its DSP I/O channels. Now and then
  a resume-all after a code swap left the thread halted. A second
  resume-all restarted it.

For the opcode tests, `scripts/dsp/isa.py` sends DSP I/O channel 0 to
Analog 1 and channel 1 to Analog 2. Mixer 1 pans them hard left and hard
right. The left channel carries 0.25 b, where b steps through a circular
group of eight state words. The right channel carries the result. Each
capture gives eight points.

The input meters hold their peaks for 2 s (`meters/peakHold`), so a level
decrease shows late. After the tests, 0xD3 with data[2] = 0 and an erase
of all threads returned the inputs to dry.

### 8.7 Open questions

- Bits 29 and 30 of 0x14. They changed nothing in the test.
- Whether bits 27:26 also make a state operand A circular.
- Why a one-word 0xD4 write changes other state words, and why a
  resume-all sometimes does not restart the thread.
- Whether the core can feed the record stream, as the FX Rack "Print"
  mode needs.
- Which caller in the vendor HAL resumes the core after a load.
- The meaning of 0xD3 data[0] and data[1] when they differ.
- Where the DSP meters land. The meter block holds 88 meters on this unit
  (4.4).

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
