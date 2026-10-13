# PSoC scheduler, interrupts, power, and EEPROM commit

**Verified:** Shutdown drains an active save, not dirty state alone. Timer allocation and factory reset also expose reproducible software defects.
Evidence: `0x204dc`, `0x20498`, `0x16eb6`, `0x20f5c`, and the offline tests below.

## Evidence and terminology

This report uses local files only. No device, service, network, or shared Ghidra project access occurred.

| Term | Definition |
|---|---|
| Verified | Direct instructions, image bytes, or explicitly identified offline execution |
| Inferred | Consequence of cited code, with the necessary execution conditions stated |
| Unknown | Available evidence does not establish the fact |
| PSoC | Cypress microcontroller that executes this application |
| FPGA | Programmable logic device at the external memory interface |
| ISR / IRQ | Interrupt service routine / interrupt request |
| NVIC | ARM interrupt controller |
| SRAM | Volatile microcontroller memory |
| EEPROM | Separate nonvolatile byte store at `0x40008000` |
| CRC | Eight-bit cyclic redundancy check, not authentication |
| Tick | One increment of the complemented TMR0 hardware counter |
| Dirty | A save request exists at `0x1fff9014` |
| Active | Incremental save state at `0x1fff902c` is nonzero |
| Source | Command origin: 0 local, 1 host, 2 EEPROM replay |
| DSI / DCFG | Digital system interconnect / digital clock configuration |
| SPC | Supervisory controller for nonvolatile memory operations |

**Verified:** `/tmp/apogee-fw/flash.bin` SHA-256 is `a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8`.
CPU addresses equal file offsets plus `0x10000`.
Function addresses omit the Thumb bit. Stored callback pointers include it.

The prior maps are `psoc-startup.md`, `psoc-protocol.md`, `psoc-update.md`, and `function-coverage.tsv` in this directory.
Thumb instructions take precedence over `decompiled.c`, particularly for memory-access order and unsigned arithmetic.

**Unknown:** No physical interrupt overlap, EEPROM failure, reset, or power transition was observed in this pass.
Offline execution establishes software behavior under the stated substitutes, not hardware behavior.

## Execution model

### Foreground order

| Status | Phase | Evidence |
|---|---|---|
| Verified | Main enables global interrupts, initializes components, timers, settings, and power state, then waits for FPGA readiness. | `0x1f90a–0x1f91e` |
| Verified | Input IRQ installation precedes FPGA IRQ installation, protocol timer registration, and FPGA event enable. | `0x1f948–0x1f95a` |
| Verified | If hardware state is not 6, main calls only the hardware progression helper in its ready-dependent section. | `0x1f960–0x1f96a`, predicate `0x10148` |
| Verified | The first ready pass resets routes with source 2. Each ready pass then calls audio restore, incremental save, and UI service. | `0x1f970–0x1f98e` |
| Verified | Every pass calls panel-event service, FPGA-event service, report service, then the timer scheduler. | `0x1f9a2–0x1f9b2` |
| Verified | The timer scheduler calls callbacks synchronously in the foreground. No separate timer ISR installs these callbacks. | `0x2033a`, vector installers `0x1fa14`, `0x1feac`, `0x22318` |
| Inferred | A blocked foreground peripheral operation prevents timer callbacks, protocol progress, and deferred power work. | All four depend on return to `0x1f9a2–0x1f9b2` |

### Five installed ISRs

All entries below are **Verified** static assignments. Vector addresses refer to the table selected by `0x21a04`.
Priority numbers are the arguments before the five-bit shift into the NVIC priority byte.

| IRQ | Handler / vector word | Priority | ISR work | Foreground protection |
|---|---|---:|---|---|
| 0 | `0x1f9b8` / `0x1fff8040` | 5 | Set `0x1fff8f88`, increment `0x1fff8f94`, disable IRQ0 through `0x22ca8`. | `0x1fa94` reads expander `0x70`, processes state, clears flag, enables IRQ0. |
| 1 | `0x1f9dc` / `0x1fff8044` | 5 | Set `0x1fff8f8c`, increment `0x1fff8f98`, disable IRQ1 through `0x22d44`. | `0x1fa94` reads expander `0x71`, processes state, clears flag, enables IRQ1. |
| 2 | `0x1fa00` / `0x1fff8048` | 7 | Set `0x1fff8f90`, disable IRQ2 through `0x23394`. | `0x1fa94` clears flag, calls `0x17660`, enables IRQ2. This precedes its hardware-ready check. |
| 6 | `0x1fd84` / `0x1fff8058` | 4 | Clear P2 interrupt status. Latch FPGA bits 0,1,2,3,5 into `0x1fff8fbc`. Update link state for bit 3. | `0x1ff6c` disables IRQ6 before the handshake and event drain, then enables it on return. |
| 15 | `0x223ec` / `0x1fff807c` | 7 | Advance the fixed I2C controller. Read/write transfer buffers and completion/error bytes. | Transfer setup and status helpers have no global interrupt guard. Exact publication order follows below. |

**Verified:** IRQ6 increments the total interrupt count at `0x1fff8fa4`, not the per-event counters.
Foreground `0x1ff6c` increments `0x1fff8fac/8fb0/8fb4/8fb8` for event bits 0/2/3/5.
These counts therefore describe service observations, not exact physical event totals.

**Verified:** `0x1fd84` sets disconnect flag `0x1fff8fd0` only when link state was nonzero.
A disconnect event while software already considers the host disconnected does not set that flag.

### Shared state and concurrency limits

| Status | Object or operation | Protection and limit |
|---|---|---|
| Verified | Panel flags and associated counters | Each ISR disables its own source before return. Foreground clears the flag before re-enable (`0x1f9b8–0x1fd48`). |
| Inferred | Multiple panel edges | A boolean flag cannot preserve an edge count. Exact coalescence depends on the expander and IRQ route, which remain unknown. |
| Verified | FPGA flags and handshake state | `0x1ff6c` masks IRQ6 across handshake, disconnect work, and up to eight message parses. Other IRQs remain enabled. |
| Inferred | FPGA events during that mask | Service waits for foreground return. Preservation of every physical event requires FPGA latch and interrupt-route evidence. |
| Verified | Timer table, settings pool, save cursor | No interrupt guard surrounds their foreground operations (`0x2019c`, `0x20230`, `0x20820`, `0x20918`, `0x211dc`). |
| Verified | Settings writes from the five ISRs | Their traced call paths do not call the settings setters, timer allocator, or EEPROM save API. |
| Inferred | Host/panel mutation during a save | This is foreground interleaving across save steps, not proof of an ISR race inside a copied chunk. |
| Verified | Control shadows at `0x1fff810c/810d` | `0x1152c/0x11578` use unguarded read/modify/write. No traced ISR calls either helper. |
| Inferred | Control-shadow race | Unguarded code alone does not establish a reachable interrupt race for these shadows. |
| Verified | Global critical-section helpers | `0x23a70`: `mrs r0, primask`, then `cpsid i`. `0x23a78`: restore PRIMASK from r0. |
| Verified | SPC lock | `0x23d1c/0x23d84` protect lock byte `0x1fff904c` and wait-pipeline state `0x1fff9050` with those helpers. |
| Verified | EEPROM write duration | `0x23064` restores interrupts after lock acquisition. It does not hold a global interrupt mask throughout the row wait. |

**Inferred:** Programmed priorities permit IRQ6 to precede lower-priority work, with IRQ0/1 above IRQ2/15.
Evidence: priority installers and AIRCR value `0x05fa0400` at `0x21a04`.
**Unknown:** Actual interrupt arrival times, overlap frequency, and state inherited from the absent bootloader.

### I2C publication order and possible races

**Verified:** The decompiler reorders transfer-field stores. It is not reliable evidence of a late buffer-pointer publication.
The actual write path stores length, pointer, and mode at `0x22818`, `0x2281e`, and `0x22824`.
It then issues START at `0x22842`, clears completion at `0x22852`, and enables IRQ15 at `0x2285a`.

**Verified:** The read path publishes length, pointer, and mode at `0x2292a`, `0x22930`, and `0x22936`.
START follows at `0x22954`, completion clear at `0x22964`, and IRQ enable at `0x2296c`.

**Verified:** `I2C_MasterClearStatus` loads status at `0x229ec`, then stores zero at `0x229f4`, without a critical section.
`I2C_MasterStatus` samples status and controller state separately at `0x229b0/0x229b6`.

**Inferred:** An ISR between these accesses can produce a stale status snapshot or discard a new status bit.
An ISR after START but before completion clear can likewise interact with that unguarded update.
**Unknown:** A hardware schedule that produces an actual lost completion on this board.
No such race was reproduced with physical interrupts or a peripheral-accurate model.

## Timer contract and computed targets

### Table and time arithmetic

All table fields are **Verified** by `0x2019c–0x2020a` and `0x20280–0x2035a`.

| Address or offset | Width | Meaning |
|---|---:|---|
| `0x1fffa0a8` | 160 bytes | Ten entries, stride 16 |
| Entry `+0` | 4 | Callback pointer. Zero means free |
| Entry `+4` | 4 | Argument |
| Entry `+8` | 2 | Period |
| Entry `+10` | 2 | Accumulated elapsed ticks |
| Entry `+12` | 4 | Enabled flag |
| `0x1fff8fd4` | 2 | Previous complemented counter sample |

**Verified:** Allocation returns the first free index plus one, or zero when all ten slots contain callbacks (`0x2019c`).
Removal accepts handles 1–10, clears callback and enabled fields, and returns one even for an already empty slot (`0x20230`).
The API has no generation value, callback validation, duplicate check, or period-zero rejection.

**Verified:** The scheduler samples the counter once, updates the previous sample, then visits slots in ascending order (`0x20286–0x20354`).
It adds elapsed ticks modulo 65536 and calls each due callback at most once.
After callback return, it clears that slot's elapsed field, without a catch-up loop or residual-period subtraction (`0x20348`).

**Verified:** Both elapsed implementations use:

```text
now = (~Counter_ReadCounter()) & 0xffff
elapsed = (now - previous - (1 if now < previous else 0)) & 0xffff
```

Evidence: `0x202a0–0x202bc`, `0x2038e–0x203aa`.
`0x203a8` loads the return with `ldrh`, not signed `ldrsh`.
The decompiler's signed return type does not describe the machine result.

| Status | Boundary | Result |
|---|---|---|
| Verified, offline | Previous `ffff`, now `0000` | Zero, despite one counter transition |
| Verified, offline | Previous 65530, now 5 | Ten, not eleven |
| Verified, offline | Previous 0, now 65535 | 65535, not a negative value |
| Verified | Equal samples | The scheduler does no work. Full wraps cannot be distinguished from no elapsed ticks. |
| Verified, offline | Accumulator 2000, delta 64535, period 65000 | Accumulator becomes 999 and the due callback does not run. |
| Inferred | Long callback or foreground stall | Later invocations run late. The elapsed accumulator can overflow before the threshold comparison. |

**Verified:** Self-removal at `0x17518` is safe for the current loop: only the elapsed field is cleared after return.
**Inferred:** Reuse of a removed slot has no stale-handle defense.
No current callback that removes and reallocates its own slot was found among the three registrations.

### Registration, removal, and nested callbacks

All literal pointers and call sites below are **Verified**.

| Registrant | Callback pointer / entry | Argument | Period | Removal |
|---|---|---|---:|---|
| Power initialization, call `0x17596` | `0x17519` / `0x17518` | 0 | 1000 | Callback clears inhibit flag `0x1fff82f8`, then removes handle `0x1fff914c` at `0x1752c`. |
| Protocol initialization, call `0x1617a` | `0x15f59` / `0x15f58` | 0 | 500 | No timer removal. Suspend selects callback state 4 at `0x1618c`. |
| Identify command, call `0x16ec4` | `0x10545` / `0x10544` | `0x1fff82e4` | 30 | Zero command removes saved handle `0x1fff8f18` at `0x16ed6`. |

**Verified:** The protocol initializer ignores allocation failure and returns one (`0x1617a–0x16180`).
Power initialization stores its handle but sets the inhibit flag without a failure check (`0x17596–0x175a4`).
**Inferred:** Their fixed startup order normally allocates the first two slots before host commands can consume slots.

**Verified:** Each nonzero Identify command allocates another timer, then overwrites the sole saved handle (`0x16ebe–0x16ecc`).
It does not remove the preceding timer or reset the shared descriptor.
**Verified, offline:** Two nonzero commands followed by zero leave the first Identify timer active.
**Inferred:** Repeated Identify requests can exhaust slots. An allocation failure overwrites the saved handle with zero and leaves older timers unreachable through cancellation.

| Status | Computed instruction | Pointer source and resolved target |
|---|---|---|
| Verified | `blx r3` at `0x2033a` | `0x1fffa0a8 + 16*index`. Three registration sources appear above. |
| Verified | `blx r3` at `0x10588` | Descriptor `+0`, RAM `0x1fff82e4`, initializer flash `0x255b4`: pointer `0x105cd`. |
| Verified | `blx r3` at `0x10578` | Descriptor `+12`, RAM `0x1fff82f0`, initializer flash `0x255c0`: pointer `0x15f21`. |
| Verified | Helper entry `0x105cc` | Returns `phase < (limit >> 1)`. This function is absent from the baseline coverage table. |
| Verified | Completion entry `0x15f20` | Dispatches local Identify value zero through `0x16fbc`. It has no direct caller in the baseline graph. |

**Verified:** The descriptor contains initial phase 0, limit 2, countdown 100, and reload 100 (`0x255b8–0x255bf`).
`0x10544` advances phase through 0,1,2, decrements the countdown, and invokes completion when countdown equals one.
**Inferred:** Leaked timers share that phase and countdown. Their combined callbacks alter the Identify duration and can outlive the cancellation request.

The following computed branches are switch tables, not unknown callback providers.
All entries are **Verified** from the bounds checks and indexed PC loads.

| PC load | Table | Index source |
|---|---|---|
| `0x1017e` | `0x10184`, 12 words | Hardware state `0x1fff8eec`, range 0–11 |
| `0x15f6c` | `0x15f70`, four words | Protocol state `0x1fff8f0c`, range 0–3 |
| `0x175d4` | `0x175d8`, five words | Power state minus one, range 0–4 |
| `0x211ee` | `0x211f4`, four words | Save state `0x1fff902c`, range 0–3 |
| `0x22426` | `0x2242c`, six words | I2C state minus `0x45`, range 0–5 |

**Verified:** Hardware exception dispatch obtains the five ISR pointers from the RAM vectors listed above.
**Unknown:** Additional targets after RAM corruption. The scheduler does not restrict pointers to these three callbacks.
The unchecked 31-word mailbox receive can overwrite the first callback (`0x120b8`, destination `0x1fffa0a8`).

### Units remain unresolved

**Verified:** Counter read `0x232bc` captures TMR0 and returns its 16-bit value. `0x20364` complements it.
TMR0 period is `ffff` (`0x23154`). The fitter sets `TMR0_RT0=4b` and `TMR0_CFG1=30`.
Evidence: configuration pairs `0x480020b2/0x480020b4`, consumed by `0x21ad4`.

**Verified:** Clock setup configures DCFG3 divider 2999 and source byte `19` (`0x21b74–0x21b80`).
**Inferred:** This provides the existing 1 kHz candidate from the nominal 3 MHz internal oscillator.
**Unknown:** A complete DCFG3-to-TMR0 route. Neither threshold values nor the candidate clock proves that route.
No millisecond conversion is promoted to Verified in this report.

## Power-state contract

**Verified:** Application power state, hardware progression, and protocol callback state are three separate variables.
Their addresses are `0x1fff8f1c`, `0x1fff8eec`, and `0x1fff8f0c` respectively (`0x17540`, `0x10168`, `0x15f58`).

The power-state names below are **Inferred** descriptions. Transitions and operations are **Verified**.

| State | Meaning from callers | Transitions and evidence |
|---:|---|---|
| 1 | Host-associated active state | Disconnect selects 2. Panel request sends power-off report, requests hardware stop, suspends protocol callback, then selects 3 (`0x175c4`, `0x17660`). |
| 2 | Standalone active state | Ready host handshake selects 1. Panel request after inhibit expiry finishes only an active save, clears control-B mask 4, selects 4 (`0x17630`, `0x17660`). |
| 3 | Software-off state | Panel request resumes protocol callback, requests hardware start, selects 1. Disconnect finishes active save, clears mask 4, selects 4 (`0x17660`, `0x175c4`). |
| 4 | Control-B mask 4 cleared | No further transition in these handlers. Physical power removal is unknown (`0x175c4`, `0x17660`). |
| 5 | Deferred restart request | Command `0x63` value 1 selects 5. Later disconnect writes restart marker, falls through the active-save drain, clears mask 4, selects 4 (`0x176e0`, `0x175c4`). |

**Verified:** Startup reads FPGA byte `0x60800004` through `0x11664`.
Zero selects state 2. Nonzero plus absent restart marker selects state 3 and requests hardware stop.
Nonzero plus valid restart marker selects state 1 and clears the marker (`0x17540`).
**Unknown:** The physical meaning of every bit in that FPGA byte.

**Verified:** The 1000-tick callback clears the initial panel-request inhibit (`0x17518`).
This is elapsed scheduler time, not a blocking delay inside the power handler.

**Verified:** Hardware state 6 admits incremental EEPROM service. States 7–11 do not (`0x10148`, `0x1f960–0x1f98a`).
Shutdown progresses through waits of at least 500, 10, and 10 elapsed ticks (`0x10168`).
**Inferred:** State 1 to state 3 can suspend both dirty-save starts and an active incremental save until resume or disconnect.
This is a main-loop gate, not a save-specific mutex.

**Verified:** Restart marker `CD AB bool 00` occupies EEPROM row 127 at `0x7f0–0x7f3` (`0x17754`).
The patch helper uses a local 16-byte buffer and does not reset the shared stream cursor (`0x13188`).
**Inferred:** A marker write between save steps does not itself overwrite the settings stream state.
Its ignored row result still prevents a durable restart-intent guarantee.

## EEPROM commit contract

### Dirty state is not active state

| Status | Address | Role |
|---|---|---|
| Verified | `0x1fff9014` | Dirty flag, updated by `0x20820/0x20918`, cleared by save start and synchronous save |
| Verified | `0x1fff9018` | Last dirty timestamp, 16 bits |
| Verified | `0x1fff902c` | Active phase: 0 idle, 1 descriptors, 2 payload, 3 CRC patch |
| Verified | `0x1fff9010/901c/9020` | Descriptor count, current descriptor index, byte offset within its payload |
| Verified | `0x1fff900c` | CRC accumulator, shared by save and validation |
| Verified | `0x1fff9084/9086/9088` | Buffered byte count, EEPROM stream offset, 16-byte row buffer |
| Verified | `0x1fffa870/0x1fffa7bc` | Temporary descriptors / corresponding live-state offsets |

Evidence: `0x203b4`, `0x20820`, `0x20918`, `0x210b0`, `0x211dc`, `0x13030–0x13188`.

**Verified:** `0x204dc` contains only the active predicate and advance loop:

```text
0x204e2  bl 0x211dc
0x204e6  bl 0x211bc
0x204ee  bne 0x204e2
```

It never reads dirty state or calls save start.
**Verified, offline:** Dirty=1 and active=0 returns without a row request and retains dirty=1.

**Verified:** `0x20498` advances an active save once, then independently evaluates dirty age.
At `0x204c6–0x204c8`, `cmp elapsed,3000` and `bls` reject elapsed values through 3000.
It clears dirty at `0x204ce` and calls `0x210b0` at `0x204d0` only when elapsed exceeds 3000.
**Verified, offline:** Age 3000 does not start. Age 3001 starts and writes row zero.

**Verified:** The worker has no second active-state check before save start.
**Verified, offline:** Dirty age 3001 with an active descriptor phase resets its cursor to 3 and writes row zero again.
**Inferred:** Slow foreground progress plus a newer dirty request can restart an unfinished save.
Actual frequency depends on tick rate, foreground delays, and request cadence.

### Row sequence and result semantics

All sequence entries are **Verified** instructions. Counts also pass offline execution with successful atomic row substitutes.

| Phase | Work | Evidence |
|---|---|---|
| Start | Build 42 persistent descriptors. Initialize CRC and stream. Write header `AE 02 2A 00` and first three descriptors. | `0x210b0` |
| Descriptor phase | Append one remaining four-byte descriptor per call: 39 calls. | `0x21204–0x21244` |
| Payload phase | Append at most 16 live bytes from one descriptor per call: 97 calls for 1119 bytes. | `0x2124a–0x212d6` |
| Final partial row | Preserve bytes beyond the used extent through a read/modify/write. Reset stream count and offset to zero. | `0x1314c`, `0x13188` |
| CRC phase | Patch byte 3 through a full row-zero rewrite. Clear active state regardless of row result. | `0x212e0–0x212ee` |
| Total | 137 advance calls after start. 81 image rows plus one extra row-zero rewrite, 82 row requests. | `0x210b0`, `0x211dc`, offline row log |

**Verified:** The image ends after offset `0x50a`. There is one copy, no alternate bank or generation marker (`0x210b0`, `0x20f5c`).
CRC covers descriptor and payload bytes, not the four-byte header (`0x20b78`, `0x20eec`).
The polynomial is `07`, initial value zero, no reflection, and no final XOR (`0x218cc/0x218ec`).

**Verified:** Application row callers discard `0x23064` results (`0x13050`, `0x130ac`, `0x13188`).
**Verified, offline:** A substitute that returns error 4 for every row still reaches active=0 and dirty=0.
**Inferred:** Completion means the software consumed its phases. It does not establish a durable commit or successful readback.

### Control mutation, reset overlap, and interrupted commit

| Status | Scenario | Established consequence |
|---|---|---|
| Verified | Host or panel changes state between save steps | The writer reads the live pool at `0x21288`, then calculates CRC from that same address at `0x2129c`. It has no snapshot. |
| Verified, offline | Change a value after its payload chunk | EEPROM retains the old value, CRC validates, and dirty remains set after active completion. |
| Inferred | Change a value before its payload chunk | That save can include the newer value. Other earlier chunks retain older values. This requires no ISR overlap. |
| Verified | Repeated unchanged host writes | `0x20918` still sets dirty and refreshes the timestamp. The one-byte setter `0x20820` requires a changed value. |
| Verified | Source 2 or command `0x23` | Neither setter triggers a save for those writes. Command `0x23` still participates in a later full save. |
| Verified | Ordinary hardware controls during active save | `0x16228` contains no active-save gate before its hardware handlers or state stores. |
| Verified | Factory reset during active save | Command `0x51`, value `AB`, selects protocol state 2. Callback `0x15f58` calls defaults and synchronous save without an active-save drain. |
| Verified, offline | Factory save overlaps descriptor phase | Synchronous save leaves active=1 and descriptor cursor=3. Its partial flush resets the stream offset to zero. |
| Verified, offline | Incremental continuation after that factory save | Descriptor 3 overwrites EEPROM byte zero with `07`, not magic `AE`. A fresh validator rejects the resulting image. |
| Inferred | Runtime reset overlap | Reachable if factory reset executes while an incremental save remains active. No physical run established the necessary schedule. |
| Verified, offline | Reset after a completed payload row, before final CRC patch | A constructed mixed old/new image with CRC zero passes the actual validator after fresh SRAM initialization. |
| Unknown | Reset during a physical row pulse | Torn-row bytes, controller recovery, and analog power behavior are not modeled. |

**Verified, offline:** The interruption test changes an early input-mode byte and the final persistent byte.
It deliberately chooses a live-state tail byte that makes the intermediate image CRC zero, then stops after modeled row 10 completes.
The row substitute writes all 16 bytes atomically. The early byte is new, the final byte remains old, and `0x20b78` accepts zero CRC.
**Unknown:** Ordinary user-state reachability of that chosen tail value and the probability of this failure on hardware.
This test proves an accepted interrupted image under the row model, not a typical power-loss outcome.
**Inferred:** CRC zero is not an invalid transaction marker. The software contract does not guarantee either the old image or the new image.

**Verified:** Validation and save share CRC and temporary-descriptor storage (`0x20b78`, `0x210b0`).
A validator call is not an observational check during an active save.
**Verified:** Failed header checks do not clear a prior true value at `0x1fff8ff8` (`0x20b78`).
**Unknown:** A normal application path that preserves that true value through such a failed check.
Normal complete replay clears it at `0x20d18`.
Offline tests use fresh validator state for rejection checks and do not inject validation into an active transaction.

## Waits and liveness

| Status | Wait | Bound or failure mode |
|---|---|---|
| Verified | I2C write `0x11050` | Initial busy loop is unbounded. Each retry polls up to 200 times with 5 µs delay, but outer retries have no limit. |
| Verified | I2C read `0x110f0` | Calls the write helper first. Read retries poll up to 200 times with 2 µs delay, but repeat until exact success status 1. |
| Verified | SPI `0x108bc`, `0x10958/0x10988`, `0x22244/0x22b94` | Status/FIFO waits have no software timeout. |
| Verified | EEPROM row `0x23064` | SPC completion loops have no timeout. Lock acquisition can return error 4, but completion waits can block forever. |
| Verified | Active-save drain `0x204dc` | No main-loop work inside the drain. Termination requires valid save state and every low-level row call to return. |
| Inferred | Corrupt active phase above 3 | `0x211dc` performs no transition but returns active=true. The drain then loops forever. |
| Verified | FPGA ready `0x11754` | At most 10000 attempts. Only a missing signature gets the 1000 µs delay. Success adds a 1200 ms delay. |
| Verified | Flash bridge `0x12370` | Up to 20000 waits of 100 µs. Callers can continue after timeout (`0x123e0/0x12444/0x124dc`). |
| Verified | Host receive `0x1ff6c` | At most eight messages, but command handlers can block. IRQ6 stays masked throughout. |
| Verified | Unexpected exception `0x21968` | Infinite loop, without a demonstrated safe output transition. |

**Inferred:** The eight-message limit bounds count, not latency.
I2C still receives IRQ15 while the foreground masks only IRQ6, so the mask alone does not deadlock normal I2C completion.
**Unknown:** A watchdog or external supervisor that guarantees recovery from these waits.
The application evidence does not establish such a guarantee.

## Safety notes

| Status | Hazard | Constraint |
|---|---|---|
| Verified | Dirty state survives the active-only drain (`0x204dc`). | Do not treat the power path as a flush of all requested changes. |
| Verified | Hardware stop disables normal save service (`0x1f960–0x1f98a`). | Preserve the distinction between dirty, active, and durable state. |
| Verified | Factory reset and incremental save share mutable save state (`0x20f5c`, `0x211dc`). | Do not use factory reset as an atomic commit operation. |
| Verified | CRC-zero partial images can validate (`0x20b78`, offline test). | Do not rely on the current header as an interruption barrier. |
| Verified | Row errors do not reach application completion (`0x13050`, `0x13188`). | Require a separate durability check before a replacement promises persistence. |
| Inferred | Control-B mask 4 has a power/reset role (`0x175c4`, `0x17660`). | Do not alter its polarity or order without board evidence. |
| Verified | Timer pointer accepts unchecked mailbox overwrite (`0x120b8`, `0x2033a`). | Do not send malformed lengths or run corruption tests on the unit. |
| Unknown | Physical recovery after interrupted EEPROM, flash, or FPGA update | No powered interruption test is authorized or proposed here. |

## Offline validation and remaining work

The script executes original Thumb bytes for timer, dispatcher, save, CRC, and validation control flow with Unicorn.
Counter reads at `0x232bc` return a chosen sample. EEPROM writes at `0x23064` atomically copy one row or return error 4.
These substitutes establish test inputs, not hardware timing or write guarantees.
The script does not emulate interrupt arrival, peripheral routes, SPC latency, torn rows, or electrical power loss.
Every function call has a one-million-instruction cap, an explicit return-PC check, and a restored-stack check.
Save progression has a 200-call limit. Descriptor progression has a 40-call limit.

```sh
uv run --offline --with unicorn python -B scripts/firmware/psoc-scheduler-check.py
uv run --offline --with ruff ruff check scripts/firmware/psoc-scheduler-check.py
uv run --offline --with ruff ruff format --check scripts/firmware/psoc-scheduler-check.py
```

These commands read local firmware and cached dependencies. They do not contact a device or service.

**Verified, offline:** Tests cover unsigned wrap arithmetic, accumulator overflow, timer exhaustion, self-removal, duplicate Identify cancellation, strict save age, active restart, and dirty-only drain.
They also cover live-state mutation, factory-save overlap, accepted interrupted CRC, and ignored row errors.

| Unknown | Required next evidence |
|---|---|
| Tick duration | Decode the actual TMR0 clock endpoint and DSI route against the register-level hardware specification. |
| Runtime I2C race | Build a peripheral-accurate interrupt model with explicit START, completion, and status semantics. |
| Physical write interruption | Obtain the controller specification and an independent recovery plan before any separately authorized hardware test. |
| Power and reset nets | Obtain board connections for the control-B mask and FPGA status byte. |
| Broader computed calls | This report resolves scheduler, nested Identify, five vector sources, and listed state tables, not every UI virtual callback. |

The companion names file adds descriptive helper names and the previously absent entry `0x105cc`.
Names describe observed behavior, not recovered original application symbols.
