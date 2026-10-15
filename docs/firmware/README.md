# Ensemble Thunderbolt firmware map

This work maps the vendor firmware and records the evidence required before a firmware change.
It does not authorize an update or establish a recovery procedure.

## Explanation

The unit contains a programmable system-on-chip (PSoC) microcontroller and a field-programmable gate array (FPGA).
The PSoC runs processor instructions. The FPGA image configures digital hardware.
The vendor package also contains a resource image for the front panel.
A digital signal processor (DSP) inside the FPGA executes programs that the host loads at runtime.

These components require separate correctness and recovery arguments.
An image checksum can detect some corrupt data. It cannot prove that code preserves an update path or safe electrical states.
A bootloader that remains intact is insufficient if the host cannot reach it.
A vendor update package is not a backup of the complete unit.

All work in this phase uses local files and public documents.
No device commands, firmware updates, bootloader entry, or hardware fault tests are authorized by this map.

## Reference

### Evidence rules

- **Verified:** the report identifies a directly observed instruction, byte sequence, test result, or primary source statement.
- **Inferred:** the report states the evidence and the additional assumption.
- **Unknown:** available evidence does not settle the claim.

A verified static property is not a verified hardware behavior.
Each report must distinguish the two.
Function names describe the analyst's interpretation unless a source match establishes the original name.

`provenance.json` records source hashes, analysis inputs, and extraction limits.
The extracted flash and configuration images contain synthetic bytes for absent rows.
Do not program those images into the unit.

### Analysis areas

Reports appear as each agent completes its work. Their presence does not imply independent review.

| Report | Scope |
| --- | --- |
| `image-format.md` | Image records, checksums, metadata, coverage, and absent contents |
| `updater.md` | Host update phases, transport, verification, and failures |
| `psoc-startup.md` | Reset, clocks, peripheral configuration, pins, and interrupts |
| `psoc-protocol.md` | Mailbox, command dispatch, reports, and persistent state |
| `psoc-audio.md` | Audio controls, converter interfaces, FPGA registers, and mute constraints |
| `front-panel.md` | Resource format, display, encoders, and touch controls |
| `psoc-update.md` | Flash writes, bootloader entry, FPGA configuration, and recovery dependencies |
| `bootloader-options.md` | Bootloader options, the read-only session plan, and recovery steps |
| `bootloader-1.20.md` | Guards of the Bootloader 1.20 component on the unit, and rules for a write path |
| `psoc-diagnostics.md` | Second pass over factory tests and hidden hardware controls |
| `psoc-scheduler.md` | Second pass over interrupts, timers, and the save contract |
| `psoc-runtime.md` | Second pass over runtime helpers and internal flash operations |
| `fpga-bitstream.md` | FPGA image decode, device evidence, and reconstruction limits |
| `fpga-reconstruction.md` | Second pass over checksum and reconstruction discrepancies |
| `hardware-recovery.md` | Physical debug access, protection, backups, and recovery prerequisites |
| `vendor-evidence.md` | Vendor documentation, chip identification, and community repair evidence |
| `verify-update-transport.md` | Independent review of host update checks and transport failures |
| `verify-memory-safety.md` | Independent review of parser, resource, and persistent-state bounds |
| `verify-recovery.md` | Independent review of flash boundaries and reset dependencies |
| `verify-mailbox.md` | Independent review of mailbox bounds and callback storage |
| `coverage.md` | Coverage snapshot, conflicts, and unresolved areas |
| `function-coverage.tsv` | Baseline functions with source maps or explicit gaps |
| `names/*.tsv` | Address names with supporting evidence |

Each symbol file has its own address context.
The updater map spans host binaries, and the FPGA map uses configuration locations.
The front-panel map also includes prefixed external-flash addresses.
Do not merge these addresses into a single CPU symbol table.

### Image accounting

CYACD is the Cypress text format for bootloader update records.
The vendor CYACD file contains 355 records, each with 288 payload bytes.

| Payload | Bytes |
| --- | ---: |
| Application flash | 90,624 |
| Application configuration area | 11,328 |
| Metadata record, including its configuration bytes | 288 |
| Total record payload | 102,240 |

The total payload is not a count of executable code bytes.
Application flash also contains constants and tables.
At flash address `0x3FFC0`, the metadata checksum is `0x73`.
It matches the negated sum of application flash and configuration bytes, modulo 256.
This agreement does not establish the absent bootloader's acceptance policy.

### Coverage limits

The initial Ghidra export lists 666 functions.
This count excludes undiscovered functions and does not measure semantic coverage.
The function index hash in `provenance.json` identifies that baseline.

A complete map also requires reset states, interrupt paths, error paths, persistent layouts, electrical dependencies, and time constraints.
A list of command handlers alone is insufficient.

## Offline checks

Run the image inspector tests:

```sh
python3 scripts/firmware/image-format-test.py -v
```

Run the resource decoder tests with Pillow, the Python image library:

```sh
uv run --with Pillow python scripts/firmware/front-panel-test.py -v
```

Run the arithmetic checks with Unicorn, the processor emulator, and verify its execution guards:

```sh
uv run --with unicorn python scripts/firmware/psoc-audio-check.py
uv run --with unicorn python scripts/firmware/psoc-audio-test.py -v
```

Run the scheduler and mailbox emulators:

```sh
uv run --with unicorn python scripts/firmware/psoc-scheduler-check.py
uv run --with unicorn==2.1.4 python scripts/firmware/verify-mailbox.py
uv run --with unicorn==2.1.4 --with capstone python scripts/firmware/verify-descriptor-writes.py
```

Run the static evidence checkers:

```sh
python3 scripts/firmware/verify-recovery.py
python3 scripts/firmware/verify-update-transport.py -v
python3 scripts/firmware/front-panel-test.py -v
```

The FPGA checks need the Mistral work tree under `/tmp/apogee-fw`:

```sh
python3 scripts/firmware/fpga-bitstream-test.py
python3 scripts/firmware/fpga-reconstruction-test.py /tmp/apogee-fw/work-fpga-reconstruction /tmp/apogee-fw/work-fpga-bitstream/mistral
```

Inspect the installed vendor image:

```sh
python3 scripts/firmware/image-format-inspect.py \
  '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsemblePSoC.cyacd'
```

Reproduce the baseline analysis in a new output directory:

```sh
scripts/ghidra/psoc.sh /tmp/ensemble-analysis-new
python3 -m unittest discover -s scripts/ghidra -v
```

The launcher requires Ghidra from Homebrew and refuses an existing project directory.
It uses register definitions from a fixed source revision.
A fresh run matched all four derived artifact hashes in `provenance.json`.
Inspect the Ghidra log for script errors and compare the hashes before use.

These commands do not access the unit.
Inspector success establishes only the documented file-format checks, not permission to flash.
Some tests require the installed vendor package or derived analysis files and otherwise report a skip.

## Plan

### Establish artifact identity

Preserve source hashes and exact tool versions.
Record which bytes originate in an update package and which bytes originate in a device backup.
Record all synthetic padding and unknown memory ranges.

### Map behavior and hazards

Trace every command to its state changes and external writes.
Trace reset, watchdog, invalid-image, and interrupted-update paths.
Record the assumptions for all inferred behavior.
Require independent review of safety-critical conclusions.

### Prove recovery independently

Identify debug access, signal voltage, protection state, and external memory devices on the actual board.
Preserve unique identifiers, calibration, bootloader contents, and protection data where access permits.
Do not unlock or mass-erase a protected chip to obtain a backup.
Such operations can destroy the data that recovery requires.

Demonstrate restoration on a spare unit before an experimental update on the only unit.
The recovery path must not depend on the firmware component under test.
Record any remaining dependency on the FPGA, bridge, power controller, or microcontroller.

### Verify a proposed change

Define the exact behavior to change and the behavior that must remain unchanged.
Use offline tests for image formats, boundary cases, protocol state, and persistent layouts.
Use processor emulation where peripheral models can represent the relevant behavior.
Document what the emulator cannot verify, especially analog controls and time constraints.

Compare the candidate with the vendor firmware under identical test inputs.
Test reset, invalid input, timeout, and interruption cases on recoverable hardware.
Keep outputs muted until the control and audio paths pass their checks.

### Authorize an update separately

Require a reviewed change, passing tests, preserved backups, and a demonstrated recovery path.
Record unresolved risks before an explicit decision to proceed.
No level of static analysis supplies an absolute guarantee against hardware failure or loss of recovery access.
