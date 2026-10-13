# PSoC runtime and supervisory services

The application commits EEPROM rows through two SPC commands, but no recovered application path selects a main-flash, NVL, or protection operation.

## Scope and evidence

PSoC means Programmable System-on-Chip. SPC means system performance controller.
EEPROM means electrically erasable programmable read-only memory. NVL means nonvolatile latch.
ECC means error correction code. This application uses the auxiliary flash area for configuration data.
RAM means random-access memory. IRQ means interrupt request. PRIMASK is the Cortex-M interrupt mask register.
GCC means GNU Compiler Collection. EABI means embedded application binary interface.
UDB means universal digital block. SPI means serial peripheral interface. I2C means Inter-Integrated Circuit.

- **Verified** identifies original instructions, measured bytes, or explicit reference-source behavior.
- **Inferred** identifies a supported name or reachability conclusion, not proof of the original build configuration.
- **Unknown** identifies an unresolved source match, silicon consequence, or absent device state.
- Addresses are CPU addresses. `flash.bin` offsets equal addresses minus `0x10000`.
- Byte intervals below exclude their final address. Other ranges state their units explicitly.
- A source match establishes semantics, not the exact Creator release or compiler version.

**Verified:** The baseline has 73 unnamed entries at or above `0x21900`, per `function-coverage.tsv`.
This report classifies all 73, including empty stubs and two compiler-internal blocks.
It also records compiler entries that the baseline omitted.
A TSV name is not an assertion that every behavior or source identity is understood.

**Verified:** Analysis used the original vendor file, extracted bytes, the baseline decompilation, and an independent Thumb disassembly.
The SHA-256 of `/tmp/apogee-fw/flash.bin` is `a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8`.
The vendor CYACD SHA-256 is `7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24`.
The image, startup, and recovery reports define the absent bootloader and synthetic extraction gaps.
No device access, updater execution, flash-tool invocation, or shared Ghidra project modification occurred.

## Reference: pinned source comparisons

| Source                                                                    | Match and limit                                                                                                                                           |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Cypress CySpc.c], version 5.50                                           | Verified semantic match for `CySpcStart`, `CySpcLoadRow`, `CySpcWriteRow`, `CySpcLock`, and `CySpcUnlock`. Exact vendor build provenance remains unknown. |
| [Cypress CySpc.h], version 5.50                                           | Status register masks, array classes, wait-pipeline bypass bit, and software lock values.                                                                 |
| [Cypress cytypes.h], lines 1315–1327                                      | Software status numbers, distinct from the SPC hardware status field.                                                                                     |
| [Cypress EEPROM component], version 3.0, `CFG_EEPROM_Write`               | Verified semantic match for `0x23064`, including failure collapse and unbounded waits. The instance prefix is not recovered.                              |
| [Cypress CyFlash.c], version 5.50                                         | Temperature globals and reference EEPROM power API. The vendor EEPROM startup differs materially.                                                         |
| [Cypress CyLib.c]                                                         | `CySoftwareReset`, `CyDelay`, `CyDelayUs`, `CyIntSetVector`, and `CyIntSetPriority`.                                                                      |
| [Cypress assembler]                                                       | Exact instruction semantics for `CyDelayCycles`, `CyEnterCriticalSection`, and `CyExitCriticalSection`.                                                   |
| [Creator Counter source]                                                  | Counter API roles and register operations. Design-specific UDB register addresses differ.                                                                 |
| [Creator I2C interrupt source]                                            | Reference state machine. No exact identity established for the vendor's empty pre-stop helper.                                                            |
| [GCC double assembly], [GCC single assembly], [GCC assembly macros]       | Six assembled Thumb-2 blocks agree after explicit equivalent encodings and call relocations. Results follow below.                                        |
| [GCC division wrappers], [GCC division helpers], [GCC integer arithmetic] | EABI quotient/remainder wrapper and 64-bit division family. C bodies lack a byte-identical rebuild.                                                       |

The GCC revision is `5ab2fe5755fdcbca49bb1c0dedb9d77cb26a13b0`, the dereferenced `releases/gcc-4.8.4` tag.
**Inferred:** This is GCC `libgcc` software arithmetic, not evidence for Arm's proprietary compiler runtime.
The original compiler version remains **Unknown**.

## Reference: SPC and EEPROM map

| Address      | API or data                                             | Status and evidence                                                                                   |
| ------------ | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `0x2304c`    | `EEPROM_Enable` variant                                 | Verified: calls only `0x23a80`. No `CySetTemp` call. Reference component Enable calls both APIs.      |
| `0x23058`    | `EEPROM_Start`                                          | Verified: calls `0x2304c`. Startup path is `0x1f8fc → 0x10074 → 0x23058`.                             |
| `0x23064`    | `EEPROM_Write(rowData, uint8 rowNumber)`                | Verified: fixed array `0x40`, exactly 16 bytes, row range 0–127. Calls all five SPC functions below.  |
| `0x23a70`    | `CyEnterCriticalSection`                                | Verified bytes: `ef f3 10 80 72 b6 70 47`. Save PRIMASK, disable IRQs, return.                        |
| `0x23a78`    | `CyExitCriticalSection`                                 | Verified bytes: `80 f3 10 88 70 47`. Restore PRIMASK, return.                                         |
| `0x23a80`    | `CyEEPROM_Start` variant                                | Verified: sets bit `0x10` in `PM_ACT_CFG12` and `PM_STBY_CFG12`. No wake-counter write or ready wait. |
| `0x23bb4`    | `CySpcStart`                                            | Verified: sets bit `0x08` in `PM_ACT_CFG0` and `PM_STBY_CFG0`, under a critical section.              |
| `0x23bf8`    | `CySpcLoadRow(array, buffer, uint16 size)`              | Verified: command `0x02`, keys `b6 d5`, array byte, then exactly `size` bytes.                        |
| `0x23c84`    | `CySpcWriteRow(array, uint16 row, polarity, magnitude)` | Verified: command `0x05`, keys `b6 d8`, array, row high byte, row low byte, polarity, magnitude.      |
| `0x23d1c`    | `CySpcLock`                                             | Verified: software lock and wait-pipeline enable, not a flash-protection API.                         |
| `0x23d84`    | `CySpcUnlock`                                           | Verified: releases software lock and restores pipeline bypass, not a flash-unlock API.                |
| `0x1fff904c` | `SpcLockState`                                          | Verified: byte, zero means free, one means owned. Accesses at `0x23d30/0x23d3a/0x23d96`.              |
| `0x1fff9050` | `spcWaitPipeBypass`                                     | Verified: saved 32-bit bypass state. Accesses at `0x23d62/0x23d9a/0x23db6`.                           |
| `0x1fffa9f0` | `dieTemperature[2]`                                     | Inferred source name. Verified byte loads at `0x230d8/0x230dc`, literal at `0x23150`.                 |
| `0x40004720` | `SPC_CPU_DATA`                                          | Verified: command/data port. Literal references only at `0x23c80` and `0x23d18`.                      |
| `0x40004722` | `SPC_SR`                                                | Verified: status port. Literal references at `0x2314c`, `0x23c7c`, and `0x23d14`.                     |
| `0x40080004` | `PANTHER_WAITPIPE`                                      | Verified: bit zero is bypass, per `CySpc.h`. Zero enables the required pipeline.                      |

### Command acceptance and completion

**Verified:** Both low-level command functions first require `SPC_SR & 2 != 0`, which means idle.
If the controller is busy, they return `CYRET_LOCKED=4` without a command.
They send the three command-prefix bytes, then require `SPC_SR & 2 == 0`, which means busy.
If that acceptance check fails, they return `CYRET_CANCELED=9` without payload bytes.
Otherwise, they send the payload and return `CYRET_STARTED=7`.
They do not wait for completion or decode the final hardware status.
The reference defines command `0x05` as erase-then-program for the selected row, with data from the row latch.
Evidence: `0x23c0c–0x23c6a`, `0x23ca6–0x23d04`, and `CySpc.c` functions of the same names.

**Verified:** Neither low-level function checks array bounds, row bounds, a null pointer, or lock ownership.
`CySpcLoadRow` also accepts arbitrary 16-bit sizes (`0x23c58–0x23c5e`).
The sole recovered caller fixes array and size. It does not accept a host-supplied array number.
Calls at `0x23092` and `0x230e0` pass array `0x40`, which the source defines as EEPROM.

| Stage in `EEPROM_Write` | Verified behavior                                                                                                         |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Power and bounds        | Calls `CySpcStart` even for an invalid row. `0x23076–0x2307a` rejects bit 7 in the narrowed row byte.                     |
| Lock                    | Calls `CySpcLock`. Failure returns 4 and does not call unlock.                                                            |
| Load latch              | Calls `CySpcLoadRow(0x40,rowData,16)`. Any result except 7 becomes `0xffffffff`.                                          |
| Load completion         | `0x2309e–0x230aa` waits indefinitely for idle. Then separate reads require idle and `SPC_SR >> 2 == 0`.                   |
| Commit                  | Only successful latch completion permits `CySpcWriteRow(0x40,row,dieTemperature[0],dieTemperature[1])`.                   |
| Commit completion       | `0x230f2–0x230fe` waits indefinitely for idle. Separate reads again require idle and hardware status zero.                |
| Release                 | Every finite path after a successful lock calls `CySpcUnlock` at `0x23130`. A permanent busy state never reaches release. |
| Result                  | Returns 0 for success, 1 for invalid row, 4 for lock conflict, or `0xffffffff` for other failures.                        |

**Verified:** SPC status bits 7:2 encode the hardware result. Bit zero is data-ready, not an error bit.
`CySpc.h` defines success 0, invalid array 1, invalid key 2, asleep array 3, and protection failure 9.
It also defines address failure 10, command failure 11, and row failure 12.
The wrapper collapses every nonzero hardware result to `CYRET_UNKNOWN`, so no distinct protection error reaches its caller.
The wrapper neither retries nor reads EEPROM back for comparison (`0x23064–0x23148`).
The two status checks use separate volatile reads, not one stable status snapshot.

### Interrupt and wait-pipeline constraints

**Verified:** PRIMASK zero means IRQs were enabled. One means they were disabled.
The decompiler's interrupt helper names obscure that polarity. Original bytes and `CyBootAsmGnu.s:129–155` establish it.
The assembly saves and restores PRIMASK. It does not unconditionally enable IRQs on exit.
The source requires interrupt handlers to preserve the interrupt mask that they inherit (`CyBootAsmGnu.s:112–116`).

**Verified:** `CySpcLock` masks IRQs only around the lock and pipeline update.
It clears wait-pipeline bypass bit zero at `0x23d56`, then executes three NOP instructions at `0x23d58/0x23d5a/0x23d5c`.
`CySpcUnlock` restores bypass only if the saved value is one.
It also executes three NOP instructions after that register write (`0x23dac/0x23dae/0x23db0`).
`CySpc.c` explicitly requires the pipeline for SPC register access regardless of CPU frequency.

**Verified:** The EEPROM wrapper does not mask IRQs across either command stream or busy wait.
The low-level send functions contain no critical-section calls.
**Inferred:** Serialization depends on cooperative lock use, not a transaction-wide interrupt mask.
The recovered IRQ handlers have no SPC caller path. They can interrupt a foreground EEPROM transaction without another identified SPC client.
**Unknown:** Timing restrictions from the exact silicon revision beyond this reference-source contract.
Do not infer that the same interrupt policy is safe for new main-flash code.

### Temperature and source-version limits

**Verified:** Startup zeroes `0x1fff8ed0–0x1fffa9f7`, including both temperature bytes (`0x21970`, descriptor at `0x253c4`).
The recovered code has no temperature-update store or `CySpcGetTemp` command.
The only explicit temperature-address literal is `0x23150`, used by the two reads in `EEPROM_Write`.
**Inferred:** Normal application commits pass `00 00`, absent memory corruption or an unmodeled external RAM writer.
**Unknown:** Whether this changes EEPROM reliability on the actual silicon.
The reference source documents temperature-dependent writes, but that does not prove a field failure.

**Verified:** The reference `CyEEPROM_Start` additionally enables the SPC clock, sets the wake counter, masks IRQs, and waits for the awake bit.
The vendor function at `0x23a80` performs none of those additional operations.
`CySpcStart` enables the SPC clock before each row write.
Do not transplant version 5.50 startup behavior into this image as an exact source reconstruction.

## Reference: caller paths and persistent data

All paths in this table are **Verified** direct calls, except the stated indirect scheduler entry.
Names for application functions follow the existing protocol and update maps.

| Entry or consumer         | Path to the row commit                                                            | Consequence                                                                                             |
| ------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Main service              | `0x1f8fc → 0x20498 → 0x210b0/0x211dc → 0x13050/0x130ac/0x1314c/0x13188 → 0x23064` | Deferred settings save. Each physical row commit still blocks.                                          |
| Synchronous settings save | `0x15f58(state 2) → 0x20f5c → stream/patch helpers → 0x23064`                     | Factory-reset path. Writes header, descriptors, values, then checksum byte at EEPROM offset 3.          |
| Finish active save        | `0x204dc → 0x211dc → stream/patch helpers → 0x23064`                              | Finishes an already active save. It does not expose a raw flash API.                                    |
| Restart marker            | `0x17540/0x175c4/0x176f8 → 0x17754 → 0x13188(0x7f0,buffer,4) → 0x23064`           | Rewrites EEPROM row 127. Marker bytes are `cd ab`, boolean intent, and zero.                            |
| Full stream row           | `0x13050/0x130ac → 0x23064`                                                       | Commits 16 bytes from RAM `0x1fff9088`. Then advances the offset and clears the buffer count.           |
| Partial stream row        | `0x1314c → 0x13188 → 0x23064`                                                     | Reads unaffected EEPROM bytes into a 16-byte stack buffer, then replaces the entire row.                |
| Arbitrary patch helper    | `0x13188 → 0x23064`                                                               | Uses direct full rows when aligned. Otherwise preserves unrelated bytes by CPU reads from `0x40008000`. |
| Bootloader request        | `0x16228 → 0x17fb4(mode 0) → 0x176f8`, then `0x232fc → 0x23ab4`                   | First attempts the EEPROM marker. Then writes reset status `0x40` and sets `RESET_CR2` bit zero.        |

**Verified:** `0x16168` registers Thumb pointer `0x15f59` with the scheduler at `0x2019c`.
The scheduler dispatches it indirectly from `0x20280`, which main calls.
Factory-reset command `0x51` selects protocol state 2 through `0x17004`, subject to byte `0xab` at `0x16f1a`.
This reaches `0x15f58 → 0x20f5c`, despite the baseline's zero direct callers for `0x15f58`.

**Verified:** Main calls `0x17540`, which can clear the restart marker after its read.
Disconnect handler `0x175c4` writes intent one in state 5, then finishes an active save through `0x204dc`.
Deferred IRQ2 service calls `0x17660`, which also reaches `0x204dc` in its shutdown path.
Neither call starts a save that is only dirty (`0x204dc`).
The bootloader request does not check marker-write success before reset (`0x17fb4`, `0x176f8`, `0x17754`).

**Verified:** All three direct callers of `0x23064` discard its return value: `0x13050`, `0x130ac`, and `0x13188`.
A failed row can therefore leave the save state advanced, with no retry or host-visible error from these helpers.
Both save paths write a zero checksum placeholder first, then patch the actual checksum at offset 3 (`0x20f5c`, `0x210b0`, `0x211dc`).
**Inferred:** This is not an atomic transaction across rows. Power loss can leave mixed old and new contents.
A zero placeholder is not an unconditional invalidity marker because a valid checksum can also be zero.

**Verified:** The descriptor table at `0x25ebc` selects 42 persistent descriptors and 1119 value bytes.
The header adds 4 bytes and descriptor records add 168 bytes, for 1291 bytes total (`0x216e4`, `0x20f5c`).
A complete save attempts rows 0–79, partial row 80, then row zero again for the checksum: 82 physical row commits.
The partial row preserves offsets `0x50b–0x50f`. The restart marker separately occupies row 127.
This extent does not reach main flash, the bootloader, or auxiliary configuration flash.

**Verified:** `0x13188` has no total EEPROM-range check. It narrows its computed row number to eight bits before `0x23064`.
Rows 128–255 fail the wrapper check. A computed row 256 narrows to row zero.
For partial rows, the preservation read still uses the untruncated address.
**Inferred:** This helper is unsafe for arbitrary caller-supplied ranges, even though the recovered callers use internal data.
This is not proof of a host-accessible raw-address command.

**Verified:** EEPROM reads at `0x13258`, `0x13188`, and the settings validator use the mapped array directly.
No recovered `CyEEPROM_ReadReserve` or `CyEEPROM_ReadRelease` implementation mediates these reads.
**Unknown:** The exact device-specific arbitration consequence. The newer reference exposes explicit reservation APIs.

### Main flash, NVL, protection, and configuration boundary

| Operation                                               | Status and evidence                                                                                                                                |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Main-flash row write                                    | No recovered application call passes flash array 0–3. The two generic SPC helpers are capable primitives, not an exposed application flash writer. |
| ECC/configuration row write                             | No recovered application path loads 256 or 288 bytes into the SPC latch. The sole size argument is 16 at `0x23090`.                                |
| Sector erase `0x08`, erase all `0x09`, row erase `0x13` | No implementation or invocation identified. Only command bytes `0x02/0x05` reach `SPC_CPU_DATA` in the recovered code.                             |
| NVL write `0x06`, protection write `0x0b`               | No implementation or invocation identified. `CySpc.c:23–42` supplies command identities, not evidence that they are linked.                        |
| Algorithm download `0x0d`, temperature `0x0e`           | No implementation or invocation identified. Their source presence does not establish binary presence.                                              |
| Flash-protection unlock or mass erase                   | `0x23d84` is not such an operation. It only changes RAM lock state and `PANTHER_WAITPIPE`.                                                         |
| Bootloader rewrite                                      | No recovered application implementation. The reset path enters an absent resident bootloader, whose commands and policy remain unknown.            |
| Metadata mutation                                       | No recovered write to `0x3ff00–0x3ffff`. `Bootloadable_Load` does not rewrite the metadata row.                                                    |
| Startup configuration                                   | Verified: `0x21ad4/0x21ccc` read auxiliary flash tables and write volatile peripheral registers. They do not program those tables.                 |
| Cache and pipeline                                      | Verified: fitter `0x21ccc` changes cache and wait-pipeline registers. These affect execution, not persistent protection.                           |
| External flash                                          | Verified: `0x123e0/0x12444` use the FPGA bridge. Those writes are separate from SPC and remain covered by `psoc-update.md`.                        |

The negative results above are **Inferred** from the full recovered function inventory, original instruction review, and command-port literal references.
They are not a proof against arbitrary corrupted control flow, computed peripheral pointers, or code in the absent bootloader.
The four target functions have one direct caller each, all within `0x23064`.
They are reachable, not unused library residue.

## Reference: compiler runtime classification

### Original-byte comparison

**Verified:** GCC assembly was assembled as Thumb-2 for `thumbv7m-none-eabi`, then compared with original byte spans.
The local LLVM assembler required three syntax adaptations in a temporary copy of `lib1funcs.S`:
`.force_thumb` became `.thumb`, `.syntax divided` became `.syntax unified`, and `.align 0` became `.align 2`.
The last change reproduces GNU Arm assembler's default four-byte alignment.
No arithmetic instructions were changed for this comparison.

| GCC build define  | Original span     | Bytes | Byte differences | Verified explanation                                                    |
| ----------------- | ----------------- | ----: | ---------------: | ----------------------------------------------------------------------- |
| `L_arm_addsubdf3` | `0x23dd4–0x24142` |   878 |               24 | Eight equivalent immediate move/add/subtract encodings.                 |
| `L_arm_muldivdf3` | `0x24144–0x24568` |  1060 |                8 | Four equivalent two-byte subtract encodings.                            |
| `L_arm_cmpdf2`    | `0x24568–0x24676` |   270 |                6 | Six unresolved call relocations. Original targets match source symbols. |
| `L_arm_fixdfsi`   | `0x24678–0x246c6` |    78 |                0 | Entire span is byte-identical.                                          |
| `L_arm_addsubsf3` | `0x246c8–0x248e4` |   540 |                4 | Two equivalent two-byte add/subtract encodings.                         |
| `L_arm_muldivsf3` | `0x248e4–0x24b82` |   670 |               12 | Six equivalent two-byte subtract encodings.                             |

The double add differences occur at `0x23fc8`, `0x23fca`, `0x24064`, `0x24084`, `0x240c8`, `0x240fe`, `0x24118`, and `0x24120`.
The compare relocations occur at `0x24606/0x24618/0x2462c/0x24640/0x24654/0x24668`.
Their targets are `0x24578/0x24604/0x24604/0x24604/0x245f4/0x245f4`, respectively.
These are explicit differences, not a blanket mask over unmatched bytes.

### Reachable arithmetic entries

All arithmetic source names below are **Verified semantic matches**, except the explicitly inferred C division entries.
A call-site address identifies the actual branch instruction, not just its parent function.

| Address   | Runtime identity                                     | Application caller evidence                                                                                    |
| --------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `0x23ddc` | `__aeabi_dsub` / `__subdf3`                          | `0x18570`, `0x1859c`. Flips the second sign bit, then falls into double add.                                   |
| `0x23de0` | `__aeabi_dadd` / `__adddf3`                          | `0x17d92`, `0x17dce`, `0x17e0a`, `0x18766`.                                                                    |
| `0x2409c` | `__aeabi_f2d` / `__extendsfdf2`                      | Six calls in `0x179ec` and `0x18638`, including `0x17d56` and `0x1872a`.                                       |
| `0x24144` | `__aeabi_dmul` / `__muldf3`                          | `0x185ae`.                                                                                                     |
| `0x24320` | Double multiply special-value block, source `.Lml_s` | Internal branch from double multiply. Not a standalone callable function.                                      |
| `0x24578` | `__cmpdf2` / `__eqdf2` / `__nedf2`                   | Called at `0x24606`, beneath `__aeabi_dcmplt`.                                                                 |
| `0x24604` | `__aeabi_cdcmpeq` / `__aeabi_cdcmple`                | Flag-result helper, called at `0x2462c`. It preserves input `r0`.                                              |
| `0x24628` | `__aeabi_dcmplt`                                     | `0x18556`, `0x1858a`. Returns a boolean less-than result.                                                      |
| `0x24678` | `__aeabi_d2iz` / `__fixdfsi`                         | `0x185be`. Converts double to signed integer with truncation toward zero.                                      |
| `0x246d0` | `__aeabi_fsub` / `__subsf3`                          | `0x1844c`, `0x18508`. Falls into single add after sign-bit change.                                             |
| `0x246d4` | `__aeabi_fadd` / `__addsf3`                          | `0x17cc2`, plus single-subtract fall-through.                                                                  |
| `0x24834` | `__aeabi_ui2f` / `__floatunsisf`                     | `0x18434`, `0x184d0`.                                                                                          |
| `0x248e4` | `__aeabi_fmul` / `__mulsf3`                          | `0x184fe`.                                                                                                     |
| `0x24a4c` | `__aeabi_fdiv` / `__divsf3`                          | `0x18440`.                                                                                                     |
| `0x24b84` | `__aeabi_uldivmod`                                   | Inferred wrapper identity from source and register contract. Calls at `0x121c2/0x12224/0x12276`.               |
| `0x24be4` | `__gnu_uldivmod_helper`                              | Inferred C-source match. Calls unsigned quotient, stores `a-b*quotient` through the stack-supplied pointer.    |
| `0x24ec4` | `__udivdi3`                                          | Inferred C-source match. Multiword unsigned division beneath `0x24be4`. Exact compiler output remains unknown. |
| `0x24c14` | `__aeabi_ldiv0` return stub                          | Inferred symbol. Verified `bx lr`, reached by the zero-divisor branch at `0x24b98`.                            |

**Verified:** The unsigned division wrapper returns quotient in `r0:r1` and remainder in `r2:r3` on its normal path.
On a zero divisor, it branches to the return stub without the normal remainder calculation (`0x24b84–0x24ba4`).
It prepares quotient zero for zero numerator, otherwise all ones.
Do not replace this with a claim that division by zero raises a software exception.

**Verified:** These arithmetic blocks contain no SPC command-port writes.
**Inferred:** Their application roles are mixer level calculations and external-rate arithmetic, from callers `0x179ec`, `0x18420`, `0x18470`, `0x18534`, `0x18638`, and `0x12150`.
A runtime name does not validate application input ranges or numerical accuracy.

### Linked entries without a recovered application path

The following entries are **Inferred unreachable under recovered control flow**, not proven unreachable under arbitrary computed jumps.
The review found no direct entry branch or stored Thumb function pointer, except internal calls within the same unused family.
Shared tails remain reachable from other entries. Do not delete a whole assembly block because one entry lacks callers.

| Entries                                               | Classification and evidence                                                                                                                |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `0x23dd4`                                             | `__aeabi_drsub`, reverse double subtraction. No direct caller. Shares `0x23de0`.                                                           |
| `0x24058`, `0x24078`, `0x240d8`, `0x240e8`            | Unsigned/signed 32-bit and 64-bit integer-to-double entries. Source symbols `ui2d/i2d/ul2d/l2d`.                                           |
| `0x24398`                                             | `__aeabi_ddiv`. No direct caller. Its shared multiply/divide code is not wholly unreachable.                                               |
| `0x24506`                                             | Double-divide special-value block, source `.Ldv_s`. Baseline incorrectly treats it as a separate function.                                 |
| `0x24568`, `0x24570`                                  | `__gtdf2/__gedf2` and `__ltdf2/__ledf2` comparison entry variants.                                                                         |
| `0x245f4`, `0x24614`, `0x2463c`, `0x24650`, `0x24664` | Reverse flag comparison and unused boolean comparison wrappers. Only `0x24628` has an application caller.                                  |
| `0x246c8`                                             | `__aeabi_frsub`, reverse single subtraction. Shares `0x246d4`.                                                                             |
| `0x2483c`, `0x24858`, `0x24868`                       | Signed 32-bit and unsigned/signed 64-bit integer-to-single entries.                                                                        |
| `0x24bb4 → 0x24c18`                                   | Inferred `__gnu_ldivmod_helper → __divdi3`, signed 64-bit division family. No caller to the wrapper. C binary equivalence remains unknown. |

### Constructor and memory runtime

| Address   | Status and classification                                                                                                                 |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `0x25134` | Verified constructor-array traversal. Calls `0x253a0`, then indirect constructor pointers. Existing name `__libc_init_array`.             |
| `0x25180` | Verified byte-copy loop with destination return, existing name `memcpy`. No overlap support.                                              |
| `0x25196` | Verified byte-fill loop with destination return, existing name `memset`.                                                                  |
| `0x253a0` | Verified register-save/restore return stub. Inferred `_init` from its sole caller `0x25134`. Exact startup-object source remains unknown. |
| `0x1003c` | Verified constructor target through word `0x253ac`. Weak-hook checks resolve to zero. Inferred GCC `frame_dummy`, not a flash service.    |

**Unknown:** Exact newlib revision, startup-object provenance, and original linker map.
The report does not certify these functions solely because their names resemble runtime symbols.

## Reference: other previously unnamed generated functions

### Empty stubs and decoder controls

| Addresses                                  | Classification                         | Evidence and confidence                                                                                                                      |
| ------------------------------------------ | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `0x221ec`, `0x221f8`                       | Preamp SPI empty enable hooks          | Verified empty bodies, called after the critical section in `0x2216c`. Inferred TX/RX interrupt-enable roles. Exact source identity unknown. |
| `0x22b3c`, `0x22b48`                       | Display SPI empty enable hooks         | Verified empty bodies, analogous calls from `0x22abc`. Inferred TX/RX roles.                                                                 |
| `0x22a60`                                  | I2C pre-stop empty helper              | Verified empty body, called in the transmit-complete branch of `0x223ec`. Original API name unknown.                                         |
| `0x22d7c`, `0x22e30`, `0x22ee4`, `0x22f98` | Four decoder Init stubs                | Verified empty bodies. Each Start calls its stub once, guarded by an initialization byte. Names inferred from the Start pattern.             |
| `0x22d88`, `0x22e3c`, `0x22ef0`, `0x22fa4` | Four decoder Enable routines           | Verified: write mask `0x0f`, then set status auxiliary-control bit `0x10` under a critical section.                                          |
| `0x22e10`, `0x22ec4`, `0x22f78`, `0x2302c` | Four decoder SetInterruptMask routines | Verified direct byte stores to B1_UDB04, B0_UDB00, B0_UDB07, and B1_UDB11 mask registers, respectively.                                      |

The instance labels Speaker, Input, Headphone1, and Headphone2 remain **Inferred** from their application consumers.
Empty bodies establish no hardware side effect. They do not establish why the generator emitted each stub.

### Counter API matrix

All register effects are **Verified** original instructions. API names are **Inferred** from the [Creator Counter source] and caller structure.
Each column belongs to the instance that its heading names.
These functions are reachable through component startup, not unused flash helpers.

| Operation          | Speaker | Input   | Headphone1 | Headphone2 | Effect                                                     |
| ------------------ | ------- | ------- | ---------- | ---------- | ---------------------------------------------------------- |
| Enable             | `2342c` | `235d8` | `23784`    | `23930`    | Sets control bit `0x80`.                                   |
| SetInterruptMode   | `2346c` | `23618` | `237c4`    | `23970`    | Writes the status mask byte.                               |
| ReadStatusRegister | `2348c` | `23638` | `237e4`    | `23990`    | Reads the status byte.                                     |
| ReadCapture        | `234e4` | `23690` | `2383c`    | `239e8`    | Reads the 16-bit capture FIFO.                             |
| WritePeriod        | `234fc` | `236a8` | `23854`    | `23a00`    | Writes the 16-bit D0 pair.                                 |
| WriteCompare       | `2351c` | `236c8` | `23874`    | `23a20`    | Writes the 16-bit D1 pair.                                 |
| ClearFIFO          | `2353c` | `236e8` | `23894`    | `23a40`    | Reads captures until status bit `0x40` clears. No timeout. |

## Safety notes

- Preserve the bootloader, NVLs, protection bytes, and auxiliary flash data. This application image does not contain their complete device state.
- Do not call the generic SPC helpers with arbitrary arrays or sizes. They have no such bounds checks.
- Do not confuse `CySpcUnlock` with a protection unlock. It cannot establish debug access or recovery.
- Preserve the wait-pipeline transition and its three NOP instructions. The reference requires the pipeline before SPC access.
- Preserve the saved interrupt mask. An unconditional enable changes the caller's state.
- Do not add an SPC client to an interrupt handler without a complete serialization review.
- Treat EEPROM busy waits as potential permanent foreground stalls. The code has no timeout or recovery path.
- Treat ignored EEPROM results as data-loss risk. A completed save state does not prove that its rows committed.
- Prevent reset and power loss during row commits. The reference EEPROM source warns of corruption during incomplete operations.
- Do not pass unbounded offsets to `0x13188`. Row truncation can redirect a write to an earlier EEPROM row.
- Do not infer safe main-flash operations from this EEPROM path. New flash code needs separate execution, protection, and recovery constraints.
- Do not treat arbitrary EEPROM edits as safe configuration changes. Replay can reach the command dispatcher and reset path.
- Do not alter temperature behavior solely from the newer reference. The silicon consequence remains unresolved.

**Verified:** `0x15f58` passes replay records from `0x20d18` to `0x16228` with source 2.
The protocol report identifies unchecked replay widths and command identities. Runtime names do not remove those application-level risks.

Evidence for these constraints is the command and caller map above, especially `0x23064`, `0x23bf8`, `0x23c84`, and `0x13188`.

## Procedure: offline verification and unresolved work

Regenerate the disassembly without device access:

```sh
python3 scripts/psoc-firmware.py > /tmp/psoc-runtime.s
```

Check the source image and extraction with the existing independent inspector:

```sh
python3 -B scripts/firmware/image-format-inspect.py \
  '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsemblePSoC.cyacd'
```

For the GCC comparison, fetch the three pinned assembly files into one directory.
Apply the three syntax adaptations above only to a temporary copy of `lib1funcs.S`.
Compile each listed define with `xcrun clang -target thumbv7m-none-eabi -D<define> -c`.
Extract `.text` with `llvm-objcopy -O binary --only-section=.text`.
Compare each span, then inspect every differing instruction and call relocation.
The table records the actual comparison, not a proposed unexecuted match.
These commands access files only. They have no device or flash risk.

**Verified:** The existing image inspector passed for the vendor file.
TSV validation passed for 109 unique records, valid kinds, address syntax, and all 73 previously unnamed baseline entries.
The report and TSV passed whitespace and prohibited-word checks.
No implementation script was needed. No device-dependent behavior was tested.

| Open question                                    | Next static evidence                                                                                                      |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| Exact Creator library release and vendor changes | Obtain the original generated sources or linker map. Resolve the missing temperature call and shorter power-enable API.   |
| Temperature relevance on this part               | Obtain the applicable silicon errata and complete SPC algorithm contract. Do not infer a defect from zeros alone.         |
| Exact integer division build                     | Rebuild pinned `libgcc` C helpers with the original toolchain, or verify their arithmetic contract independently.         |
| Empty SPI/I2C hook identities                    | Obtain matching generated component versions. Retain descriptive names until then.                                        |
| Indirect reachability outside recovered roots    | Resolve every application callback and inspect the absent bootloader. Absence of direct callers is not a universal proof. |
| EEPROM failure behavior                          | Model busy-forever, rejected command, nonzero hardware status, row 127/128/256, and reset between physical rows offline.  |
| Physical recovery and protection state           | Obtain existing factory artifacts. No device readback or programmer command is proposed.                                  |

## Primary sources

[Cypress CySpc.c]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/CySpc.c
[Cypress CySpc.h]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/CySpc.h
[Cypress cytypes.h]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/cytypes.h
[Cypress EEPROM component]: https://raw.githubusercontent.com/eltradec/SCSI2SD-Proc/bac90efb2aaafa9168b5520a62ed180cc04470ef/creator/SCSI2SD.cydsn/Generated_Source/PSoC5/CFG_EEPROM.c
[Cypress CyFlash.c]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/CyFlash.c
[Cypress CyLib.c]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/CyLib.c
[Cypress assembler]: https://raw.githubusercontent.com/Infineon/CyScope/fa1d1eacbccedbf621325660e7aec2894766fbed/ScopePSoC/Scope.cydsn/Generated_Source/PSoC5/CyBootAsmGnu.s
[Creator Counter source]: https://raw.githubusercontent.com/tewtal/tasbot/d6cc8053429b7b099c186dd49c248ead29be347c/TASBot.cydsn/Generated_Source/PSoC5/ClockCounter.c
[Creator I2C interrupt source]: https://raw.githubusercontent.com/SBannwarth/I2C/0892663dd73d4ba2f17f12279c170b90301add3e/I2C_FF.cydsn/Generated_Source/PSoC5/I2C_1_INT.c
[GCC double assembly]: https://raw.githubusercontent.com/gcc-mirror/gcc/5ab2fe5755fdcbca49bb1c0dedb9d77cb26a13b0/libgcc/config/arm/ieee754-df.S
[GCC single assembly]: https://raw.githubusercontent.com/gcc-mirror/gcc/5ab2fe5755fdcbca49bb1c0dedb9d77cb26a13b0/libgcc/config/arm/ieee754-sf.S
[GCC assembly macros]: https://raw.githubusercontent.com/gcc-mirror/gcc/5ab2fe5755fdcbca49bb1c0dedb9d77cb26a13b0/libgcc/config/arm/lib1funcs.S
[GCC division wrappers]: https://raw.githubusercontent.com/gcc-mirror/gcc/5ab2fe5755fdcbca49bb1c0dedb9d77cb26a13b0/libgcc/config/arm/bpabi.S
[GCC division helpers]: https://raw.githubusercontent.com/gcc-mirror/gcc/5ab2fe5755fdcbca49bb1c0dedb9d77cb26a13b0/libgcc/config/arm/bpabi.c
[GCC integer arithmetic]: https://raw.githubusercontent.com/gcc-mirror/gcc/5ab2fe5755fdcbca49bb1c0dedb9d77cb26a13b0/libgcc/libgcc2.c
