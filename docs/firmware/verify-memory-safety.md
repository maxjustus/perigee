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

## Safety notes

- Do not send slot lengths above 29 through any host implementation.
- Do not send update packets where `p1` exceeds the actual payload length.
- Do not install a resource image without the offline decoder's validation.
- Do not edit EEPROM descriptors without an offline validator.
- Treat report word counts as advisory. Compare them with the record layout.
