# Plan: an open driver for the Apogee Ensemble Thunderbolt

Companion to `NOTES-vendor-driver.md`. That file records what the vendor
binary does. This file records what we do not know, what we build, and in
which order.

## 1. What the notes do not settle

The notes describe one working sequence. They do not describe the hardware
contract. Four gaps remain. Each needs the device attached.

| Gap | Question | Why it matters |
|-----|----------|----------------|
| Register order | Must `NUMBER_OF_CHANNELS` precede the address registers? Must the DMA "arm" bit settle before "run"? | A wrong order can hang the FPGA with no error |
| PSoC behavior | How does the PSoC parse bad input? What do the 8 header bytes mean? Is one doorbell per slot required? What order does Get-all answer in? | The mailbox is the only path to sample rate and clock source |
| Persistent state | Which settings survive a power cycle? Which must the host restore at attach? | The vendor HAL restores a snapshot on every connect. A driver that skips it inherits stale state |
| Interrupt semantics | Is `CUR_OUTPUT_AUDIO_ADDRESS` live and precise mid-stream? Do `INTERRUPT` bits 22 and 26 give a finer period than one wrap? | Decides the clock model (section 3, item 2) |

## 2. Probe first

No driver code before the probe answers section 1. The vendor kext exposes
`AccessBAR0Register` (user client method 6) and `ReadBAR0Block` (misc
request 13). A user-space tool can read registers while the vendor HAL
plays audio.

Steps:

1. Open `com_apogeedigital_ElemEnsUserClient` with `IOServiceOpen`. The
   vendor HAL holds the single client slot. If open fails, unload the HAL
   plugin for the probe session and use the kext alone.
2. Read `ID`, `STATUS`, `INFO`, `GENERAL`, `INTERRUPT` at idle. Record them.
3. Start playback in the vendor HAL. Sample `CUR_OUTPUT_AUDIO_ADDRESS_LOW`
   and `CUR_INPUT_AUDIO_ADDRESS_LOW` at 1 ms for 5 seconds. Check that the
   values advance monotonically and wrap at `channels * 0x4000 * 4` bytes
   from the ring base.
4. Read `STATUS` under underflow. Pull the cable. Read all registers again.
5. Send a Get-all (type 4) through `SendRequest` and log every notification
   packet. Record the order and the command IDs.
6. Power-cycle the unit with no host. Reconnect. Send Get-all again. Diff
   against step 5. The diff is the persistent state.

Deliverable: `probe/` tool and `probe-results.md`. The plan below assumes
step 3 succeeds. If it fails, item 2 of section 3 reverts to the vendor
clock model.

## 3. Design

The kernel/user split is forced by macOS. Kernel code maps BAR0 and owns
DMA memory. User code implements `AudioServerPlugIn`. Inside that boundary
the design departs from the vendor in five places.

1. **DriverKit dext, not a kext.** `PCIDriverKit` with `IOUserClient`
   methods. Third-party kexts require reduced security on Apple silicon.
   This change is not optional.
2. **Position from hardware, not from an interrupt count.** The vendor
   computes `sampleTime += 0x4000` per MSI. One missed interrupt shifts the
   clock forever. If the probe confirms `CUR_*_ADDRESS` is live, the HAL
   plugin reads it each IO cycle and uses the MSI only as a wrap marker.
3. **PSoC mailbox in user space.** The kext runs a timer, a FIFO, and a
   parser in the kernel for a protocol that touches neither DMA nor
   interrupts. The dext maps BAR0 offsets 0x400 to 0xBF0 into the plugin as
   one region. The plugin runs the mailbox. The dext shrinks to: map,
   allocate, arm, interrupt.
4. **One unit, one device.** No `Ensemble2AudioSystem` layer, no
   Thunderbolt topology sort, no multi-unit sync pauses. CoreAudio
   aggregate devices cover multiple units.
5. **Standard properties first.** Sample rate, clock source, channel names.
   The 109 Apogee Control selectors are a later compatibility layer, if
   that goal is kept at all.

Kept from the vendor: the 32-bit integer frame-interleaved ring, and meter
DMA on the hardware timer.

### 3.1 Components

| Component | Language | Responsibility |
|-----------|----------|----------------|
| `EnsembleDext` | C++ (DriverKit) | Match 0x220119C2. Map BAR0. Allocate two rings and one timestamp page. Handle one MSI. Expose user client |
| `EnsembleHAL.driver` | Rust, `cdylib` | `AudioServerPlugIn`. Owns format, IO, mailbox, properties |
| `probe/` | Rust CLI | Section 2. Also the regression tool for every later step |

Language rationale:

- The dext must be C++. DriverKit has no C ABI. `iig` emits C++ classes
  that subclass `IOService` and `IOUserClient`. The dext holds about 400
  lines and almost no logic, so a Rust core behind a C++ shim gains
  nothing.
- `AudioServerPlugIn` is a C API. The host loads a `CFPlugIn` bundle, calls
  one exported factory, and receives `AudioServerPlugInDriverInterface`, a
  struct of C function pointers. Rust reaches it through `coreaudio-sys`
  (bindgen over `AudioServerPlugIn.h`). IOKit calls (`IOServiceOpen`,
  `IOConnectCallMethod`, `IOConnectMapMemory64`) come from `io-kit-sys` or
  a hand-written `extern "C"` block.
- The probe uses the same IOKit bindings. It is the smallest piece, so it
  proves the FFI layer before the plugin depends on it.

Rust constraints:

- `DoIOOperation` runs on the real-time audio thread. No allocation, no
  lock that a non-real-time thread can hold, no logging.
- The factory symbol named in `Info.plist` under `CFPlugInFactories` must
  be a `#[no_mangle] extern "C"` function with the exact name.
- The bundle is `EnsembleHAL.driver/Contents/MacOS/EnsembleHAL`, built as
  a universal `cdylib` (arm64 + x86_64) and code-signed.

### 3.2 Dext user client

| Method | Purpose |
|--------|---------|
| `Open`, `Close` | Single client |
| `MapRegion(type)` | 0 playback ring, 1 record ring, 2 timestamp page, 3 mailbox window (BAR0 0x400 to 0xBFF), 4 meter buffer |
| `ReadReg(offset)`, `WriteReg(offset, value)` | Offsets below 0x100 only. The mailbox goes through the mapped window |
| `Start(depth)`, `Stop` | Section 3.5 of the notes |
| Async notification | One event per MSI with the current timestamp pair |

### 3.3 Order of work

Each step ends with a passing test and one commit.

1. Probe (section 2).
2. Dext: match, map BAR0, read `ID`. Test: `ReadReg(0)` returns the same
   value the probe saw.
3. Dext: allocate rings and page, write address and size registers. Test:
   registers read back the IOVA.
4. Dext: MSI. Test: timestamp page advances at the expected wrap rate under
   the vendor-equivalent register sequence.
5. HAL: one stream each way, 48 kHz only, format `lpcm` int32 packed.
   Test: sine out on Analog 1 read back on Analog 1 with a loopback cable.
6. HAL: mailbox, sample rate, clock source. Test: rate change survives a
   Get-all round trip.
7. HAL: input channel names, meter buffer exposure.
8. Optional: Apogee Control selectors.

## 4. Risks

- Contiguous 2.3 MB allocations fail on a fragmented system. The vendor
  tells the user to reboot. Mitigation: allocate at first match and hold.
- The PSoC firmware may require a host handshake we have not seen because
  the vendor HAL performs it inside `Ensemble2Command` on connect. Step 5
  of the probe records the full connect sequence to check this.
- Firmware below PCI revision 0x56 refuses DMA. Read config 0x08 before
  any allocation and refuse to match.
- Hot unplug returns all ones on every register. Every register read must
  check for 0xFFFFFFFF and stop.
