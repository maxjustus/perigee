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

The kext uses 20 Hz. The buffer holds `numHostMeters` 16-bit values plus 4
bytes. The exact position of the 4-byte word is unverified. The HAL polls
this buffer (`_updateMeters`). Meter DMA runs whenever a user client is
attached, independent of audio.

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
| 2 | type, cmd, p1, p2, len, data[len] (len <= 100) | 2 + ceil((len - 3) / 4) |

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

| ID | Name | Type | p1 | p2 / data |
|----|------|------|----|-----------|
| 0x01 | AnalogInputType | 1 | channel (0..11) | type |
| 0x02 | MicGain | 1 | channel (0..11) | gain |
| 0x03 | InstrumentGain | 1 | channel | gain |
| 0x04 | SoftLimit | 1 | channel | mode |
| 0x05 | PhantomPower | 1 | channel | bool |
| 0x06 | PhaseInverse | 1 | channel | bool |
| 0x07 | GroupID | 1 | channel | group |
| 0x08 | HighPassFilter | 1 | channel | bool |
| 0x0A | InsertEnable | 1 | channel | bool |
| 0x0D | AnalogOutputReferenceLevel | 1 | channel | level |
| 0x0E | AnalogOutputTrim | 1 | channel | trim |
| 0x0F | MainOutputMode | 1 | mode | |
| 0x10 | ActiveSpeakerSet | 1 | set | |
| 0x11 | OutputAttenuation | 1 | monitor output | attenuation |
| 0x12 | OutputMute | 1 | monitor output | bool |
| 0x13 | OutputDim | 1 | monitor output | bool |
| 0x14 | OutputSumToMono | 1 | monitor output | bool |
| 0x15 | OutputRouting / OutputPairRouting | 1 | destination | source |
| 0x16 | FrontGuitarOutputMode | 1 | channel | mode |
| 0x19 | TalkbackMicOn | 1 | bool | |
| 0x1A | OpticalPortFormat | 1 | port | format |
| 0x1C | FrontGuitarOutputAttenuation | 1 | channel | value |
| 0x1D | FrontGuitarMatchUnityGainMode | 1 | channel | bool |
| 0x1E | InputChannelPairAllocation | 1 | count (1..255) | |
| 0x1F | OutputChannelPairAllocation | 1 | count (1..255) | |
| 0x20 | KeyboardVolumeControl | 1 | monitor output | |
| 0x21 | MeterPeakHold | 1 | value | |
| 0x22 | MeterOverHold | 1 | value | |
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
| 0x38 | MixerChannelIsVisible | 2 | mixer | channel, 1 byte |
| 0x39 | MixerChannelIsStereo | 2 | mixer | channel, 1 byte |
| 0x3A | MixerChannelSoloSafe | 2 | channel | 1 byte |
| 0x50 | FunctionalTestMode | 1 | mode | |
| 0x51 | FunctionalTestResetAll | 1 | 0xAB | |
| 0x5C | DSPCoreTransfer | 2 | | see HAL `doDSPCoreTransfer` |
| 0x60 | FirmwareUpdateDFUMode | 1 | firmware type | |
| 0x61 | FirmwareUpdateComplete | 1 | firmware type | 1 |
| 0x62 | FirmwareUpdatePacket | 2 | | packet bytes |
| 0x63 | RestartPSocFirmware | 1 | reset type | |
| 0x66 | MultiUnitSettings | 2 | | 2 bytes |
| 0x90 | MixerIsPreFader | 2 | mixer | 1 byte |
| 0x91 | DAWMixerFaderLevel | 2 | mixer | channel, 2 bytes big-endian |
| 0x92 | DAWMixerPan | 2 | mixer | channel, 1 byte |
| 0x93 | DAWMixerMute | 2 | mixer | channel, 1 byte (inverted) |
| 0x94 | DAWMixerRouting | 1 | bool | 0x80 |
| 0xA0 | OpticalIsSubMix | 1 | bool | |
| 0xD3 | DSPCoreRouting | 2 | | 3 bytes |
| 0xD6 | DSPCore load/erase/coefficients | 2 | | 4 bytes |
| 0xD7 | DSPCoreHaltResume | 2 | | 4 bytes |

DAW fader level: `uint16 = (clamp(dB) + offset) * scale`, byte-swapped.
The constants are in the HAL at `setDAWMixerFaderLevel`, unverified here.

### 5.7 Reports from the PSoC

`Ensemble2AudioDevice::packetFromHardwareArrived` switches on the command
ID. Report IDs 0x01 to 0x2A echo the setter IDs above with the current
value. Extra report IDs:

| ID | Meaning |
|----|---------|
| 0x40 | Device status (not decoded) |
| 0x41 | External clock lock. data[0] != 0 = locked |
| 0x42 | Device ready. The HAL then requests all properties |
| 0x43 | Not decoded |
| 0x52, 0x53 | Functional test result (not decoded) |
| 0x61, 0x64 | Firmware update status (not decoded) |

A Get-all request (type 4) returns one report per property.

---

## 6. User client interface

Class `com_apogeedigital_ElemEnsUserClient`. The HAL opens it with
`IOServiceOpen(service, task, 0)`. One client at a time. On client death the
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
Mach message: `msgh_id = 0x13`, size 0x98 = 24-byte header + 120-byte
packet.

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

## 8. Notes for a new driver

### 8.1 Minimum viable data path

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

### 8.2 Watch items

- The FPGA never reports a status bit for the MSI. A shared vector cannot
  be disambiguated. Keep one vector.
- Firmware below revision 0x56 refuses DMA. Read PCI config 0x08 first.
- Hot unplug returns 0xFFFFFFFF from `0x7E0`. Every register read returns
  all ones after unplug.
- The kext never touches `HOST_CONTROL`, `STATUS` bits, or the
  `CUR_*_ADDRESS` registers. A new driver can use `CUR_*` for position
  instead of the wrap interrupt. This is unverified.
- The PSoC message slots hold 8 entries. Queue in software when full.

### 8.3 Unverified items

- Bit layouts of `STATUS`, `HOST_CONTROL`, `INTERRUPT` bits 22 and 26.
- Meter buffer word layout.
- `_Ensemble2ClockSource` and other enum values. The HAL has them in
  jump tables under `Ensemble2AudioDevice::*`.
- The two header words of the PSoC wire messages. The HAL sends 1, the
  PSoC reply header is copied but never read.
- The timer period of 10 ms. The vtable slot matches `setTimeoutUS(10000)`
  with one slot of tolerance.
