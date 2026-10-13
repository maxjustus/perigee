# Firmware map coverage audit

The six PSoC name maps cover 447 of 666 discovered functions, but they do not establish complete behavior or safe replacement firmware.

## Explanation

### Scope and evidence

This audit checks completeness and cross-report consistency, not every instruction claim.
It uses local reports, name maps, the baseline function index, and selected decompiler paths.
No device access, firmware execution, updater execution, or commit occurred.
Only this report and `function-coverage.tsv` belong to this audit.

PSoC means programmable system-on-chip, the application processor.
FPGA means field-programmable gate array, the separate programmable hardware.
DSP means digital signal processor, the runtime instruction engine inside the FPGA.
CPU means central processing unit. RAM means random-access memory. UI means user interface.
I2C means Inter-Integrated Circuit, and SPI means Serial Peripheral Interface.
EEPROM means electrically erasable persistent memory. DMA means direct memory access.
NACK means negative acknowledgement. FIFO means first-in, first-out peripheral buffer.
Ghidra is the disassembler and decompiler that produced the baseline.
Thumb is the processor instruction encoding used here.
A baseline function means an entry in `/tmp/apogee-fw/functions.tsv`, not a proven source-language function.
A named function means an exact baseline entry address with at least one `kind=function` row in the six selected maps.
An alias means another name for the same entry address.

**Measured** identifies a file calculation in this audit.
**Reported evidence** identifies a claim in another report, without a new instruction-level proof here.
**Audit inference** identifies a completeness consequence.
**Unresolved** identifies evidence that the next pass must supply.

The function-count snapshot time is **2026-10-13 15:54:04 UTC**.
These first-pass counts remain frozen before the diagnostic, scheduler, runtime, and FPGA follow-up passes.
The final report incorporates the later active-save correction and README revision, with their revised hashes below.
Startup and FPGA reports and maps were present and included.
The final recount also includes the front-panel Identify aliases that arrived during this audit.
The README lists `verify-memory-safety.md`, but that report was not available at this snapshot.
Its absence denotes a pending independent review, not a permanent coverage gap.

Paths without a directory below refer to `docs/firmware/`, except `decompiled.c` and `functions.tsv`, which refer to `/tmp/apogee-fw/`.
CPU addresses refer to the PSoC unless explicitly qualified.
Report line references apply to the hashed snapshot, not future revisions.

### What the percentages mean

A name proves an index association only.
A useful behavior contract also needs inputs, outputs, state changes, external writes, caller conditions, error paths, and time constraints.
A safety argument additionally needs the electrical effects, reset states, and an independent recovery path.
No supplied ledger measures those obligations per function.
Consequently, the percentage of understood or proven functions is **unknown**, not 67.12%.

The baseline itself is incomplete as a code census:

- The exporter counts Ghidra bodies through `f.getBody().getNumAddresses()` (`scripts/ghidra/ExportDecompiled.java:28`). These are not executable-byte proofs.
- Its caller counts use `f.getCallingFunctions(monitor).size()` at the same line. They do not establish complete indirect-call reachability.
- The importer seeds four vectors: `private static final int VECTORS = 4` (`scripts/ghidra/PSoCSetup.java:22`). Application code later installs RAM vectors.
- It marks the entire imported flash executable: `flash.setPermissions(true, false, true)` (`scripts/ghidra/PSoCSetup.java:32`). Constants and synthetic gaps remain in that block.
- The baseline reset body is already a counterexample to literal decompiler trust. `decompiled.c:3` says `Removing unreachable block` at `0x10024`.
  `psoc-startup.md:87` instead identifies the bytes after `0x10018` as compiler support, not a reset safety loop.

Measured: 26 baseline functions have zero recorded callers. Seventeen of these lack selected-map names.
Zero callers does not mean dead code. Timer and page callbacks require data-reference analysis.
The constructor at `0x1003C` and callback at `0x17518` illustrate distinct reachability questions (`decompiled.c:17–27,5348–5376`).

The vendor supplies 90,624 application main-flash bytes, including data (`image-format.md:94–95`, “354 rows”).
It supplies no array-zero bootloader and no complete device backup (`image-format.md:226–244`, “Array 0”).
Neither 666 functions nor 90,624 bytes measures all actual code in the unit.
FPGA circuits, runtime DSP programs, the absent bootloader, and other programmable board components need separate inventories.

## Reference

### Exact discovered-function snapshot

The count uses only these six files and only rows whose kind equals `function`.
It compares numeric entry addresses exactly, without range matches or implicit Thumb-bit conversion.
It excludes `names/updater.tsv` and `names/fpga-bitstream.tsv` entirely.
It also excludes resource offsets, tables, data, and FPGA registers within the selected maps.

| Selected map | All rows, without header | Function rows | Exact baseline matches | Entries exclusive to this map |
|---|---:|---:|---:|---:|
| `names/psoc-startup.tsv` | 162 | 134 | 134 | 101 |
| `names/psoc-protocol.tsv` | 151 | 86 | 86 | 71 |
| `names/psoc-audio.tsv` | 165 | 104 | 104 | 91 |
| `names/psoc-update.tsv` | 64 | 41 | 41 | 18 |
| `names/front-panel.tsv` | 301 | 138 | 138 | 115 |
| `names/image-format.tsv` | 16 | 0 | 0 | 0 |
| Total before address deduplication | 859 | 503 | 503 | 396 |

| Measurement | Result |
|---|---:|
| Unique named baseline functions | **447 / 666 = 67.117117%** |
| Unmapped baseline functions | **219 / 666 = 32.882883%** |
| Addresses with multiple function-map entries | 51 |
| Additional alias rows beyond unique addresses | 56 |
| Function-map addresses absent from baseline | 0 |
| Sum of all baseline body sizes | 78,626 bytes |
| Sum of named baseline body sizes | 61,046 bytes, 77.640984% |
| Sum of unmapped baseline body sizes | 17,580 bytes |

Body-size sums are descriptive weights only.
They do not establish unique byte coverage, correct boundaries, instruction coverage, or execution-path coverage.
All measurements derive from the input hashes below.

`function-coverage.tsv` contains every baseline entry, in baseline order.
Its columns preserve the original name, body size, caller count, callee count, aliases, and exact source-map lines.
The `name_status` column does not assign semantic confidence.
The file contains 666 data rows and has SHA-256 `5c3b3c81db39ef77b38fa29d604ae9d056024fa5591459d0dbd84679bea00543`.

### Unmapped clusters

The ranges below are exclusive at the upper endpoint.
Cluster labels describe address neighborhoods, not proven module boundaries.
The inventory supplies each exact unmapped address.

| CPU range | Neighborhood | Baseline functions | Unmapped | Unmapped body bytes |
|---|---|---:|---:|---:|
| `[0x10000,0x132A4)` | Peripheral helpers | 123 | 31 | 1,588 |
| `[0x132A4,0x153C4)` | DSP and audio controls | 63 | 19 | 1,866 |
| `[0x153C4,0x17518)` | Protocol and grouped state | 25 | 2 | 36 |
| `[0x17518,0x17790)` | Power state | 9 | 4 | 308 |
| `[0x17790,0x18874)` | Mixers and update | 26 | 11 | 744 |
| `[0x18874,0x1F8FC)` | Front-panel and diagnostic paths | 180 | 77 | 6,790 |
| `[0x1F8FC,0x203B4)` | Events and timers | 20 | 2 | 76 |
| `[0x203B4,0x21968)` | Settings and checksums | 37 | 0 | 0 |
| `[0x21968,0x23BB4)` | Startup and generated peripherals | 153 | 46 | 1,110 |
| `[0x23BB4,0x23DDC)` | Supervisory controller support | 5 | 5 | 488 |
| `[0x23DDC,0x253AC)` | Compiler and library candidates | 25 | 22 | 4,574 |
| Total | | 666 | 219 | 17,580 |

The next pass must distinguish absent names from absent explanations:

- **Documented but unnamed:** event helpers `0x11614/0x1167C/0x116F8` appear in `psoc-protocol.md:70–74`, “event-clear bit”.
  Display-current helpers `0x10B28/0x10B74` appear in `front-panel.md:224–225`, “RGB precharge current” and “RGB drive current”.
  Output handlers `0x14B98/0x14BD8/0x14C2C` appear in `psoc-protocol.md:307–309` with their unchecked indices.
  These entries need map synchronization, not a claim of wholly unknown behavior.
- **Safety-relevant omissions:** power functions `0x17540/0x17630/0x17660` lack names and a unified transition contract.
  `decompiled.c:5357–5375` combines a persistent marker, a timer, and control bit 2.
  `decompiled.c:5424–5449` combines power state, reports, audio shutdown, and protocol suspension.
- **Diagnostic behavior beyond display tests:** `0x1F26C` is only summarized as “invokes test code” (`front-panel.md:278`).
  It calls `0x13000` in modes 1 and 2, and `0x12FD0` on exit (`decompiled.c:11009–11036`).
  Those calls alter the front-microphone converter mode (`psoc-audio.md:310–318`).
  Related unnamed functions `0x1F0C0–0x1F444` produce commands `0x52/0x53` and consume encoder/button state (`decompiled.c:10888–11116`).
- **Supervisory writes:** all five functions at `0x23BB4–0x23D84` lack names.
  `0x23BF8/0x23C84` write supervisory command bytes, while `0x23D1C/0x23D84` change a lock and wait-pipeline state (`decompiled.c:15303–15429`).
  Their command/status and critical-section contracts need primary-source matches before any nonvolatile-write redesign.
- **Library candidates:** `0x23DDC–0x24EC4` resemble arithmetic support, but resemblance is not a source match.
  Identify calling conventions, shared tails, exceptional arithmetic, and divide-by-zero behavior before replacement.
  Baseline four-byte bodies at `0x23DDC/0x246D0` especially need boundary review (`functions.tsv:643,654`).

### Cross-report consistency and name risks

The selected maps contain 51 shared function addresses.
The audit found no definite pair of incompatible function meanings among those aliases.
Most differences describe the same operation at different levels.
The following exceptions or qualifications matter to the next pass.

| Status | Evidence | Consequence |
|---|---|---|
| Resolved report mismatch | Main independently checked `0x20498/0x204DC`. The corrected `psoc-update.md:260–265` now says “It does not start a save for dirty state alone”. | This agrees with `psoc-protocol.md:550` and `decompiled.c:11893–11904`. The end-to-end dirty-save contract before shutdown remains unresolved. |
| Conditional safety claim | `psoc-audio.md:78` says `0x14F54` “performs full mute and cancels the release timer”. `psoc-update.md:70–72` states the `0x1FFF912F` condition. | `decompiled.c:3777–3782` contains `if (DAT_1fff912f != '\0')`. Prove the caller invariant or retain the condition in the audio contract. |
| Overly narrow alias | `names/psoc-update.tsv:11` names `0x14F54` `Outputs_MuteForUpdate`. The audio report also calls it on external lock loss. | The name must not imply that only update paths reach it. Preserve both callers in a merged call graph. |
| Request versus outcome | `names/psoc-startup.tsv:103` names `0x232FC` `Bootloadable_Reset`. `names/psoc-update.tsv:39` uses `Bootloadable_Load`. | Both describe a software request. Neither proves bootloader selection or successful recovery (`psoc-update.md:235–243`). |
| Resource-cache shorthand | `names/front-panel.tsv:85` calls `0x1C5D4` `PanelResource_GetCRC`. `psoc-update.md:214–216` says “caches it” and “does not clear the cached-CRC flag”. | A name alone hides stale-cache behavior. A reload is not proof of a fresh complete-resource checksum. |
| Overlapping register consumers | `names/psoc-audio.tsv:144` names `0x60800018` `FPGA_ExternalClockPeriod`. `hardware-recovery.md:80` describes identity reads from `0x60800018` down to `0x60800011`. | `0x11B74` and `0x12150` read the shared address. Reconcile byte order, 64-bit shifts, and FPGA decode before one exclusive register meaning. |
| Known packet discrepancy | `psoc-protocol.md:499–500` says the prior probe labels command `0x90` as type 2, while this image selects type 1. | Use archived raw packets and the exact firmware identity. Do not repeat the unsafe Get-all probe. |
| Reset timing shorthand | `hardware-recovery.md:82` says command `0x51` “calls `0x205CC` and saves defaults”. `psoc-protocol.md:62–63` says it selects state 2. | The eventual action does not imply a synchronous parser-side reset. Include deferred execution in the power-state model. |

Other apparent disagreements are different evidence levels, not contradictions:

- Startup infers a 1 ms counter unit but explicitly leaves the route unknown (`psoc-startup.md:226–235`). Audio and panel reports retain raw ticks.
- `hardware-recovery.md:41` lists published chip candidates. `psoc-audio.md:46` leaves part identities unknown. No schematic or verified component match closes that gap.
- Host transport review distinguishes a logged timeout from a discarded structured status (`verify-update-transport.md:157–195`). The updater report retains that distinction.
- FPGA structure now has stronger evidence than the older size-only inference. It still lacks a complete circuit model (`fpga-bitstream.md:73–88,343–350`).

### Unresolved high-priority obligations

These are gaps in proof, not new claims that every corresponding defect occurs on hardware.
“Blocking” here means necessary before a safety argument for the affected modification.

| Priority and obligation | Existing evidence and exact gap | Concrete next offline result |
|---|---|---|
| Blocking: boot and recovery | `psoc-startup.md:95` asks “Who preserved that reset status”. `psoc-update.md:293` says fallback is “unproven”. Array 0, nonvolatile latches, protection, and lower external-flash contents are absent. | Obtain existing vendor or archival artifacts. Produce reset-cause, valid-image, transport-entry, and flash-permission contracts. Keep unavailable artifacts explicit. |
| Blocking: electrical outputs | `psoc-startup.md:372` says “No complete route” for controls A/B at `0x4000647A/0x40006476`. `psoc-audio.md:208` states no explicit phantom discharge delay. | Decode control bits through PSoC logic to pads. Correlate existing schematics or photographs with supplies, reset, mute, relays, phantom control, and bus ownership. |
| Blocking: FPGA semantics | `fpga-bitstream.md:6–8` reports 192 embedded-checksum disagreements, 12 clock gaps, and a failed semantic rebuild. The code, mixer, and flash interfaces lack proven internal destinations. | Resolve decoder discrepancies with reference designs. Trace `0x6080002E`, `0x60800C00`, audio controls, mailbox, and boot selection to actual logic and memory. |
| High: complete power-state contract | `0x17540`, `0x17660`, and `0x10168` span startup, host disconnect, button events, and shutdown. The active-save distinction above changes persistence assumptions. | Produce one state-transition table with guards, timer callbacks, persistent writes, register writes, and reentry behavior. Include commands `0x50/0x51/0x60–0x63`. |
| High: interrupts and shared state | Five vectors are mapped, but route/edge modes remain unknown (`psoc-startup.md:438–454`). Global interrupts precede component setup (`:105`). | Trace every handler, enable/disable/clear operation, shared variable, and priority interaction. Model events during initialization, masked intervals, and deferred service. |
| High: faults and forward progress | The default handler “loops forever” at `0x21968` (`psoc-startup.md:101`). FPGA readiness failure still permits initialization (`psoc-update.md:285`). Watchdog and brownout policies remain unknown (`:297–303`). | Enumerate all infinite loops, failed polls, default branches, fault vectors, and ignored results. Record outputs that remain active and the repair path that remains reachable. |
| High: timer and service deadlines | `0x20378` loses a wrap tick. `0x20280` uses ten callback slots and 16-bit accumulation (`decompiled.c:11721–11836`). Clock routing and maximum service latency lack proof. | Test wrap boundaries, long stalls, slot exhaustion, callback removal/reuse, and repeated Identify requests. Calculate bounded service latency only after bus and clock contracts exist. |
| High: peripheral error semantics | I2C and SPI waits can be unbounded (`psoc-audio.md:532`). I2C electrical rate is unknown (`psoc-startup.md:386`). The I2C ISR at `0x223EC` has no complete transition/error table. | Source-match the generated component version. Trace NACK, arbitration loss, repeated start, bus-busy, FIFO overflow, and status clear behavior. Include supervisory-controller errors. |
| High: memory and dispatch | The named settings cluster still contains unsafe replay (`psoc-protocol.md:570–587`). A 31-word slot overwrites a timer callback (`:136`). Resource copies precede integrity checks (`psoc-update.md:188–190`). | Build instruction-level offline tests for mailbox lengths, indices, resource counts, EEPROM widths, and every handler's data consumption. Include indirect calls and stack bounds. |
| High: physical flash contract | The application omits a tail length write and ignores bridge errors (`psoc-update.md:156–166`). Device page geometry remains unresolved (`verify-recovery.md:61`). | Model every erase/program/read boundary and interruption. Trace FPGA transaction length, write gate, stale buffers, chip status, and timeout propagation. |
| High: persistent identity and calibration | `hardware-recovery.md:78` says calibration locations and checksums are “Unknown”. The Thunderbolt controller and other programmable chips remain unknown (`:45`). | Inventory every nonvolatile target and every write-capable path. Separate unit identity, factory trim, user state, calibration, and firmware artifacts. |
| High: diagnostic and UI callbacks | The 77 unnamed panel entries include test modes, page callbacks, meters, and popup state. Commands reach active objects beyond the main switch (`psoc-protocol.md:194–198`). | Enumerate each callback table and all command-to-widget effects. Prove bounds, queue behavior, converter-mode restoration, and the effect of command `0x24`. |
| High: audio numeric and timing contract | The CPU checks cover ten coefficient cases and three pan cases (`psoc-audio.md:553`). FPGA mix saturation, state-copy behavior, and analog response remain unproved. | Extend boundary tests across gains, pans, rates, routes, hardware variants, and DSP chunks. Separate arithmetic equivalence from electrical safety. |

A safe-state command is not yet a proven safety mechanism.
The mute helper itself requires working peripheral paths, and converter initialization clears its global mute bit (`psoc-audio.md:81–85`).
Resource count at most 126 is only one bound, not a safe resource-update recipe (`front-panel.md:484–489`).
Checksums, unchanged vendor order, and a preserved bootloader do not replace the missing electrical and recovery evidence.

### Reproducibility and later verification status

The following later confirmations do not change the frozen 447-function count:

- **Resolved active-save wording:** Main independently checked `0x20498/0x204DC` and corrected `psoc-update.md:260–265`.
  Dirty-state preservation across shutdown remains an open behavior contract.
- **Resolved baseline overwrite and header-source risks:** `scripts/ghidra/psoc.sh:9–16` rejects existing projects and pins the header commit.
  Main reports a failed-before/fixed-after guard test and byte-identical regeneration of all four baseline artifacts.
  This establishes current-host reproduction, not every future tool environment.
- **Resolved emulator false-success risks:** `scripts/firmware/psoc-audio-check.py:18–19,84–86` rejects optimized Python and instruction-limit termination without a return.
  Main reports three guard tests and all 13 original arithmetic cases passed.
  The guard tests reside at `scripts/firmware/psoc-audio-test.py:18–40`.
  Peripheral models and electrical safety remain outside these arithmetic checks.
- **Mailbox verification result pending report:** Main reports 616 successful checks from `verify-mailbox.py`.
  The report was not available for this audit. This result is not a second independent review by this audit.

| Gap or resolved item | Evidence | Required offline action |
|---|---|---|
| Baseline regeneration still depends on installed tools | `scripts/ghidra/psoc.sh:16` now pins the register-header commit. Line 18 still uses `brew --prefix ghidra`, without a version gate. | Preserve the header hash, Ghidra version, Java version, analysis options, and import log. Verify an existing cached header too. |
| Shared-project overwrite risk resolved | `scripts/ghidra/psoc.sh:9–12` now rejects an existing project with “Choose a new output directory.” | Retain this guard. Use a separate output directory for the next discovery pass. |
| No instruction/data completeness export | `scripts/ghidra/ExportDecompiled.java:25–34` exports functions and bodies, not all instruction ranges, literal pools, indirect targets, or unresolved references. | Export those sets separately. Compare discovered code against supplied bytes, not synthetic fill. |
| Register labels are not physical evidence | `scripts/ghidra/PSoCSetup.java:40` names an address block `dma`. Startup finds no application DMA component but leaves inherited state unknown (`psoc-startup.md:419–429`). | Treat imported names as leads. Match addresses and bit fields against the correct silicon reference. |
| Some validation is prose-only | Startup reports seven malformed-input cases (`psoc-startup.md:511–513`). Protocol reports 65,536 checksum comparisons (`psoc-protocol.md:607`). Their reproduction sections do not supply persistent tests for those complete checks. | Preserve executable fixtures, expected results, input hashes, and command lines for each claimed check. |
| Test totals are not semantic coverage | Front-panel cites four decoder, seven DSP, and 39 control-model tests (`front-panel.md:471–472`). The control transport is fake. Recovery byte anchors are “consistency checks” (`verify-recovery.md:280`). | Identify which tests execute actual instructions, which test host models, and which only compare bytes. Record negative cases and unmodeled hardware. |
| Temporary analysis products | FPGA records reference temporary `.bt` files, logs, memory dumps, and a locally adapted build (`fpga-bitstream.md:322–326,396–427`). | Preserve those artifacts, hashes, source patch, and environment together. A pinned decoder commit alone does not preserve the analysis. |
| Architecture and historical evidence | `updater.md:30` states “Cross-architecture equivalence is unknown”. Protocol retains a packet discrepancy at `:499–500`. | Compare host slices offline and archive raw prior captures with firmware hashes. Do not equate historical probes with the current unit state. |
| Pending independent parser review | `README.md:57` lists `verify-memory-safety.md`. It was not available for this snapshot. | Integrate the completed review and tests before the next safety decision. Do not count its temporary absence as a permanent missing module. |

### Input hashes

These hashes identify the exact audit inputs. They do not certify their conclusions.
FPGA and updater name maps are hashed for namespace identity but excluded from every PSoC coverage calculation.
The provenance file retains vendor-source identities. This audit did not acquire device contents.

| Input | SHA-256 |
|---|---|
| `/tmp/apogee-fw/functions.tsv` | `f302cb79ae01fde3feec7b1d7183b61136420d973f48352cfe678d7d90735815` |
| `/tmp/apogee-fw/decompiled.c` | `b2419650eea38074f2d187337e8f001beb0f48c40280f537a9f08cdae99e312b` |
| `/tmp/apogee-fw/flash.bin` | `a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8` |
| `/tmp/apogee-fw/config.bin` | `7f6b8abed75862dd5ec93365dc972be00b7b133eaf6d6e3d94603dc8955e9479` |
| `docs/firmware/provenance.json` | `eec978bba2d246b47cdeb8c1a359892283523f748ee3d47637ecad452fb3bda2` |
| `docs/firmware/README.md` | `f1543454a0adefa8e61aef33a63c371c6edb273432962929c818fa965992f032` |
| `docs/firmware/fpga-bitstream.md` | `7bb1884bd36bc0f1514df85140e891b81da606b4e8f5e65196fc3817cee37af4` |
| `docs/firmware/front-panel.md` | `bc258da633e0f49ff232a292a8495d45e1eb066b2982d4cfff55e60435b318fa` |
| `docs/firmware/hardware-recovery.md` | `dc919b8674951341dcc4439ec9e7f52c02271a92e07b5cba0dcbd9d3e598fb36` |
| `docs/firmware/image-format.md` | `19e36b16f7cf9df2d36cc3da28ad5fc3e2b4d46895bf7fb178649035b98dd12c` |
| `docs/firmware/psoc-audio.md` | `ffb65509c218610da2467763d2aca9dc3ef1cea1253e150283c892c7a520765d` |
| `docs/firmware/psoc-protocol.md` | `f06f23eeba4dcb97aaae6c98a69a2279113ffd78b75e0b770a4ed4a04b2b8d67` |
| `docs/firmware/psoc-startup.md` | `3492b9c8919ec2e0e1f1aaa519adfdfab3432c5de1562fae813d7bad91545bc6` |
| `docs/firmware/psoc-update.md` | `6d6b4190e660f788c284027aeea6859fb234e32852c5aa04cc1fffbfe76906bd` |
| `docs/firmware/updater.md` | `8b32b451d6a05578db71ea566280b06560ba5ccdad58c2230f2528c44ed8ed21` |
| `docs/firmware/verify-recovery.md` | `ddc865461b433ef601cf08d5190178e91d25d1cc10c16ac88bfd5e1dc1879d3b` |
| `docs/firmware/verify-update-transport.md` | `69aca7ed9961a29a254e81c5000aee97b28f7bab2e3ad96980d2d087ff1cf030` |
| `docs/firmware/names/fpga-bitstream.tsv` | `2edc53826767c3913d6362de1a2bf749edddbdd354cee91750b575cd3068d774` |
| `docs/firmware/names/front-panel.tsv` | `874cf35d317e81113fff3166a9c43aceb8a47b2516606cb16f8515aea800ef85` |
| `docs/firmware/names/image-format.tsv` | `f0267e1843fa44f6a6d6e0b0f8d4aea44b02ad606a678b1cc88a02c663f11bd7` |
| `docs/firmware/names/psoc-audio.tsv` | `d6a71779377b5c15b284a5a5d651b83cc49f7696756dd80a19f5d9cb2579d34e` |
| `docs/firmware/names/psoc-protocol.tsv` | `4212af903a8e5db4c8a1d5d5847129d74d7e14c9b8c7a76d590fac5ce89dff5d` |
| `docs/firmware/names/psoc-startup.tsv` | `c6cdde9fd1812c4e355558573956a72755f1d67c576789ff8dcac015ff1b1e4b` |
| `docs/firmware/names/psoc-update.tsv` | `a82cc39538dfc4af09d0952775e5fcb9d138efeab89a862e5ec2e809e33bd4b4` |
| `docs/firmware/names/updater.tsv` | `1c86ea7063a0e5f55afe7dd9fe8babd26ecff90683ebb0fe8ec4ae55ee934b95` |
| `scripts/ghidra/psoc.sh` | `9c497e6afdc26486dd16d37da95dd4fb720a2bff1bef4df205c60f5e79485091` |
| `scripts/ghidra/PSoCSetup.java` | `a99baec8487e2d6fb2879ce770e3e77ef6fa63325777aea3770a7ec18dc0c6cb` |
| `scripts/ghidra/ExportDecompiled.java` | `4c2c005704b010603233cfeebe3eac6775bb038a97d3b2c2befdea4e7ca631f8` |
| `scripts/firmware/psoc-startup-decode.py` | `6cb368ad80365dc82dca7ba854f8f6480fb29d459678005374e809f2092104cb` |
| `scripts/firmware/psoc-protocol-map.py` | `b403fdbe1289ade438820e609428440dc90ce6c25d72c8131e137efa173eefc3` |
| `scripts/firmware/psoc-audio-check.py` | `8b3e4bbc9b31bd65c43d740a4f9170f8691861e60dd5f6ab91e1ca4e4b1d742d` |
| `scripts/firmware/psoc-audio-test.py` | `d4232abeae8354f5db82c47765cf30dcda52c83151cf6b1f38ad19d507d583c2` |

## Plan

### Next targeted pass

- **Preserve evidence:** archive the hashed inputs and temporary FPGA artifacts before any regeneration.
- **Close immediate semantic gaps:** prove the dirty-save contract, conditional mute, diagnostic converter modes, and supervisory-controller commands first.
- **Establish reachability:** export instruction ranges, indirect targets, vectors, callbacks, and all external writes in a separate Ghidra project.
- **Complete names without false confidence:** add aliases for already documented helpers, then source-match generated peripherals and arithmetic support.
- **Build executable contracts:** test parser bounds, power transitions, interrupt interleavings, timer wrap, and failure propagation against actual instructions where feasible.
- **Decode physical dependencies:** complete PSoC routes, FPGA bridge logic, clocks, and reset selection against existing documents and reference designs.
- **Retain unavailable evidence:** mark absent bootloader, calibration, board connections, and recovery artifacts as blockers, not tasks solved by more function names.

No hardware task follows automatically from this plan.
A bounded patch needs proof for its affected behavior and dependencies.
Replacement firmware needs the complete platform contract, including boot, errors, time, peripherals, and electrical states.
This audit guides another pass. It is not a completion or safety certificate.

### Recount without hardware access

Run this from the repository root against the hashed inputs:

```sh
python3 - <<'PY'
import csv
from pathlib import Path

baseline = list(csv.DictReader(
    Path('/tmp/apogee-fw/functions.tsv').open(), delimiter='\t'))
entries = {int(row['entry'], 16) for row in baseline}
names = ('psoc-startup', 'psoc-protocol', 'psoc-audio',
         'psoc-update', 'front-panel', 'image-format')
named = set()
for name in names:
    path = Path('docs/firmware/names') / (name + '.tsv')
    for row in csv.DictReader(path.open(), delimiter='\t'):
        if row['kind'] == 'function':
            named.add(int(row['address'], 16))
if len(entries) != 666 or len(baseline) != 666 or named - entries:
    raise SystemExit('Baseline or map contract changed')
print('named', len(named), 'unmapped', len(entries - named))
PY
```

Expected snapshot output: `named 447 unmapped 219`.
The audit checks passed for 666 inventory rows, 503 alias references, 32 input hashes, body-size sums, and the inventory digest.
Markdown table structure, whitespace checks, and the compiled recount also passed.
These checks validate the audit artifacts, not firmware behavior.
A changed count requires new hashes and a new audit snapshot, not an adjusted safety percentage.
