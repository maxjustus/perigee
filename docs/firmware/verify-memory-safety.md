# Independent verification of parser and persistence bounds

This review checked the reported memory-safety defects against the original Thumb instructions.
All four core defects are confirmed at instruction level.
External reachability and exploitability remain unresolved.

## Scope and method

Input: `/tmp/apogee-fw/flash.bin`, 196,608 bytes, SHA-256
`a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8`.
Capstone decoded the cited instructions directly from those bytes.
The related emulators in `verify-mailbox.py` and `psoc-scheduler-check.py` exercise adjacent paths.
No whole-path offline reproduction ran for the defects below.
No device access occurred.

## Claim verdicts

| Claim | Verdict | Key instruction evidence |
|---|---|---|
| `0x62` uses `p1` as the byte count, independent of the payload length | **Confirmed** | `0x16F50`: `ldrb r3, [r3, #9]` loads the count from the message. `0x16F56`: the handler receives data pointer and count. The parser copies at most 99 data bytes. The handler accepts up to 255 |
| The resource parser copies entries before the CRC check, without a count cap | **Confirmed** | `0x1C53A–0x1C576`: the loop reads the 16-bit header count and copies eight bytes per entry. `0x1C57E`: the CRC compare follows all copies. Entry index 126 reaches `0x1FFF9F68`, a live read-state variable |
| EEPROM replay copies the descriptor width without an end bound | **Confirmed** | `0x20DCC`: the only check is `start < 0x7F0`. `0x20DF4`: the copy writes to caller offset 11 for the full byte-sized width. The periodic caller supplies a 112-byte buffer, so widths above 101 overwrite caller stack state |
| Type-2 lengths 1 to 3 advance the record pointer by three words | **Confirmed** | `0x1556E–0x155A4`: the word count adds `+2` and a remainder term. For lengths 1 to 3 the total advance is three words. The record body occupies two words |
| Types 3 and 4 leave the record pointer unchanged | **Confirmed** | `0x15608–0x15610` advances the word counter only. The record pointer at frame offset `0x8C` is not updated in those cases. A later record after a Get or Get-all is therefore skipped |
| The serializer floors the word count for lengths above three | **Confirmed** | `0x15C02`: `asrs r3, #2` divides without a remainder term. The parser adds the remainder at `0x1558E–0x15598`. A length such as eight therefore reports one word less than the parser consumes |
| The serializer truncates the `0x41` version report | **Confirmed at instruction level** | Report `0x41` carries eight data bytes. The floor count reports space for seven. A host that trusts the count loses the final word |

## Consequence limits

**Confirmed.** The `0x62` defect is an out-of-bounds source read.
It reads beyond the parser's local data area within the caller frame.
It does not overflow the 256-byte update buffer while the update state is intact.

**Confirmed.** The resource defect can overwrite live state before validation.
The vendor file contains 126 entries, which fits exactly.
A header count of 127 overwrites the read-state variable.
The CRC rejection arrives after the copies.

**Confirmed.** The EEPROM gate checks magic `AE 02`, at most 44 descriptors,
an aggregate size below 2032 bytes, and a valid CRC.
It does not validate command identifiers or descriptor widths against the compiled table.
A valid-CRC EEPROM edit can therefore reach arbitrary dispatcher identifiers through replay.

**Inferred.** The parser pointer defects are format and control-flow defects.
They drop or skip records. They are not demonstrated memory corruption.

**Unknown.** Complete external reachability, whole-path effects, and exploitability.
No claim here establishes arbitrary code execution.

## EEPROM descriptor write path

**Confirmed.** No mailbox command writes EEPROM descriptor bytes with host-chosen content.
The replay width defect is therefore not reachable through the host send channel.
The host deny list needs no more commands for it.

Reproduce each range with `scripts/firmware/psoc-protocol-map.py <start> <end>`.
Reproduce the caller sets and the emulator results:

```sh
uv run --with unicorn==2.1.4 --with capstone python scripts/firmware/verify-descriptor-writes.py
```

| Step | Evidence |
|---|---|
| One row writer | `0x23064` writes every EEPROM row. Its only direct callers are `0x13050` (`0x13084`), `0x130AC` (`0x13116`), and `0x13188` (`0x13220`, `0x13234`) |
| Descriptor bytes | `0x20EEC` streams four descriptor bytes through `0x13050`. Its only direct callers are the save functions `0x20F5C` (`0x2101E`), `0x210B0` (`0x21186`), and `0x211DC` (`0x21218`) |
| Descriptor source | `0x20EB8` copies bytes 0 to 3 of a `SettingsDescriptors` entry at `0x1FFF8BEC` into the save temporaries at `0x1FFFA870` (`0x20F96`, `0x210EA`) |
| Table origin | Startup copies the table from flash `0x25EBC`. The only store into it is `0x203F6` in `0x203B4`, a halfword at entry offset 4. Bytes 0 to 3 and the volatile flag in byte 7 have no writer |
| Lookup users | `0x21738` and its wrapper `0x204F4` return an entry pointer to ten call sites. They load through it. `0x21790` bounds p1 and p2 against the entry counts and writes only stack locals. The pending-bit stores at `0x2089E`, `0x20910`, and `0x209AA` target the report table that `0x21854` returns |
| Other EEPROM writes | `0x17754` writes the restart marker at fixed offset `0x7F0` (`0x17784`). `0x21088` and `0x212E6` patch the CRC byte at offset 3. `0x1314C` flushes the stream buffer |
| Known stray stores | Commands `11` to `13` store at `0x1FFF9110+3*p1` to `0x1FFF9112+3*p1` (`0x14BC2`, `0x14C18`, `0x14C6C`). Command `94` stores at `0x1FFF90B6+p1` (`0x140D6`). All four start above the table end, `0x1FFF8DCC`, and grow upward |

**Confirmed.** A host can change saved values and can start a factory save with command `51`, value `AB`.
Neither path changes descriptor bytes. Every save writes the compiled descriptors.

**Confirmed by emulation.** The PSoC harness ran 31,768 host messages that the dext accepts.
They cover every allowed command with p1 from 0 to `FF`, type-1 values, and type-2 lengths 1 to 99.
No message wrote the table. A Get-all returned 936 reports and wrote nothing to the table.

**Confirmed by emulation.** 28 messages stopped before the end of their run.
The script checked the table up to each stop.

| Command | Stop |
|---|---|
| `38`, p1 `20` | Exceeded the 2,000,000-instruction budget at `0x21776` |
| `50`, eight p1 values | Polled hardware at `0x109F2` and exceeded the budget |
| `94`, p1 `FF` | Wrote FPGA offset `0x1133C`, outside the 64 KiB window that the harness models |

**Unknown.** A memory-corruption path outside this table could still reach `0x1FFF8BEC`.
The review covered the documented stray stores, direct calls, and the emulated messages only.

## Safety notes

- Do not send slot lengths above 29 through any host implementation.
- Do not send update packets where `p1` exceeds the actual payload length.
- Do not install a resource image without the offline decoder's validation.
- Do not edit EEPROM descriptors without an offline validator.
- Treat report word counts as advisory. Compare them with the record layout.
