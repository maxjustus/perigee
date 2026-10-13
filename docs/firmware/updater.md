# Ensemble Thunderbolt updater

The Ensemble updater uses two image transports, not one: PSoC bootloader packets and FPGA/resource mailbox packets.

## Explanation

### Scope and evidence

This report covers static analysis of the installed vendor files. It does not establish a safe update or recovery procedure.
No device access, updater execution, driver activation, or firmware write formed part of this analysis.

The programmable system-on-chip (PSoC) runs the application and exposes the update command handlers.
The field-programmable gate array (FPGA) exposes the remote inter-integrated circuit (I2C) carrier and external-flash registers.
The hardware abstraction layer (HAL) plug-in translates Core Audio properties into vendor commands.
The kernel extension (kext) implements the host register operations.

Evidence prefixes identify an artifact and an architecture. Addresses are unslid virtual addresses, not universal-file offsets.

| Prefix | Artifact                                                             | Architecture             |
| ------ | -------------------------------------------------------------------- | ------------------------ |
| U      | `Apogee Firmware Updater.app/Contents/MacOS/Apogee Firmware Updater` | arm64                    |
| H      | `ApogeeElementEnsemble.driver/Contents/MacOS/ApogeeElementEnsemble`  | arm64                    |
| K      | `ApogeeElementEnsemble.kext/Contents/MacOS/ApogeeElementEnsemble`    | x86_64                   |
| P      | PSoC application extracted from `EnsemblePSoC.cyacd`                 | Cortex-M3, Thumb         |
| F      | Bundled image or property-list file                                  | File bytes or named keys |

**Verified** means that instructions or file bytes establish the stated property.
**Inferred** identifies a consequence that also requires an explicit assumption.
**Unknown** marks a limit of the available evidence.
Cross-architecture equivalence is unknown. In particular, K does not describe the arm64e kext slice.

### The two paths

| Image                      | App-to-HAL carrier                                  | Device-side carrier                                                                                                   | Evidence                                                                 |
| -------------------------- | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `EnsemblePSoC.cyacd`       | Text header and text rows through `AEFU`, element 1 | `0x60`, selector 0, requests bootloader entry. Image bytes then use remote I2C and bootloader commands `0x37`/`0x39`. | U `0x10001117c`, `0x10001d508`; H `0x87c1c..0x87c9c`, `0x88614..0x887dc` |
| `E2FPGA.bin`               | Binary data through `AEFU`, element 3               | `0x60`, selector 2; `0x62` data; `0x61`, selector 2                                                                   | U `0x1000124d0`, `0x10001ca64`; H `0x88070..0x88190`                     |
| `EnsembleResourceData.bin` | Binary data through `AEFU`, element 2               | `0x60`, selector 1; `0x62` data; `0x61`, selector 1                                                                   | U `0x10001246c`, `0x10001ca64`; H `0x87f18..0x88034`                     |

Thus, `0x60–0x62` do **not** carry every image.
The PSoC application accepts selector 0, records a bootloader request, and resets.
It does not copy PSoC image bytes through its `0x62` handler. [Verified: P `0x17fb4`, `0x176f8`, `0x17754`, `0x232fc`; H `0x8852c`]

A bootloader alone is insufficient for recovery.
The host must also reach the remote-I2C carrier through the Thunderbolt device, driver, and FPGA registers.
[Inferred dependency: H `0x151c..0x1654`, `0x240b0`; K `0x3d24..0x4011`, `0x5fa0`]

## Reference

### Artifact identity

The app resides in `/Applications/Utilities/Apogee Firmware Updater.app`.
The analyzed HAL resides in `/Library/Audio/Plug-Ins/HAL-disabled/ApogeeElementEnsemble.driver`.
The kext resides in `/Library/Extensions/ApogeeElementEnsemble.kext`.
The disabled HAL path is an analysis input, not evidence that Core Audio loaded that plug-in.

| File                              |   Bytes | SHA-256                                                            |
| --------------------------------- | ------: | ------------------------------------------------------------------ |
| Updater executable                | 1388256 | `5a7cc6f89b61d954a3b41a3a7b80373ebcc80a7ba6fe94865e4f4f7d77e348d2` |
| HAL executable                    | 3354688 | `f23805d2e8a32b04aa135dd392f7f99d1b81751b0365c8f13f5a935147933809` |
| Kext executable                   |  380656 | `4ecc3889b80f27b150307ca2ed299a070e402cb6aff0a8f6234da8e34062eb01` |
| `EnsemblePSoC.cyacd`              |  209463 | `7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24` |
| `E2FPGA.bin`                      | 1813864 | `b3ef52ae2d1e255307e286d92f2dc92f8dccc06f0f58f7eb1c55a6cbbc4ffdf2` |
| `EnsembleResourceData.bin`        |  230036 | `3febcf6f14123ca9767fe651a87fc6fd5ba875dbe52fadf0b3160ce73bdb290b` |
| `ElementsUpdateVersionInfo.plist` |    3091 | `19b338a60ee83ea98a97300508f0fd12c782ce0adf11e4da171ce999cc06e7de` |

These values derive from complete local file reads.
The executable hashes identify whole universal files, not individual slices.
`lipo -info` identifies updater/HAL slices as x86_64 and arm64, and kext slices as x86_64 and arm64e.

### Selectors and phase state

These namespaces differ. Do not substitute an enum ordinal for a wire selector.

| Meaning           | `ElementFirmwareType` | Wire selector |      `AEFU` element | Evidence                                              |
| ----------------- | --------------------: | ------------: | ------------------: | ----------------------------------------------------- |
| Hardware revision |                     0 |          None | Not an image update | U reflection `0x1000267cc`, translation `0x10001ca64` |
| Main PSoC         |                     1 |             0 |                   1 | U `0x10001ca64`, `0x10001d508`                        |
| Main FPGA         |                     2 |             2 |                   3 | U `0x10001ca64`, `0x10001d508`                        |
| Main resources    |                     3 |             1 |                   2 | U `0x10001ca64`, `0x10001d508`                        |

The separate `EnsembleUpdateFirmwareIndex` order is PSoC, resources, FPGA.
The `ElementsFirmwareIndex` order is hardware, PSoC, FPGA, resources.
[Verified: U reflection `0x100026d28`, `0x100026de4`]

The app sends a property-list dictionary with a `PropertyData` data object.
It uses selector `AEFU` (`0x41454655`), global scope, and wire selector plus one as the element.
[Verified: U `0x10001d508..0x10001d798`, `0x10001d938..0x10001da58`]

The HAL maintains progress at object offset `+0x498` and image selector at `+0x6a4`.
The progress values are idle 0, active 1, complete 2, and failed 3.
An update-enable property resets progress to 0 and image selector to sentinel 3.
[Verified: H `0x84ef0..0x84f34`, `0x81d80..0x81ec8`, `0x87aa8..0x87e24`]

For binary images, the first property call starts the selected image when progress is 0, 2, or 3.
While progress is 1, nonempty data supplies bytes and empty data requests completion.
The app start/stop wrappers use the same property carrier, not distinct device opcodes.
[Verified: U `0x10001d8e0..0x10001daf0`; H `0x87f48..0x88008`, `0x880a0..0x88164`]

### Version decisions and phase execution

| Rule                                                                                                         | Static evidence                                      |
| ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------- |
| The controller reads target versions and force flags from `ElementsUpdateVersionInfo.plist`.                 | U `0x10000e8bc`, `0x10000e470`                       |
| Hardware versions come from the selected subdevice version dictionary.                                       | U `0x10000e314..0x10000e46c`                         |
| Version equality compares all three bytes, not a numerical greater-than relation.                            | U `0x10001c864..0x10001c894`: three `cmp` operations |
| Phase setup clears both phase lists. A reported PSoC version of `0.0.0` selects a PSoC-only phase.           | U `0x10000f820..0x10000f95c`                         |
| Otherwise, the candidate order is PSoC, FPGA, then resources for Ensemble.                                   | U `0x10000f988`, `0x10000fa10..0x10000fa14`          |
| A candidate enters the phase if both versions exist and differ, or if they match and its force flag is true. | U `0x10000fae4..0x10000fb40`                         |
| Phase execution consumes that array in order. A phase can contain multiple images.                           | U `0x10000fef4..0x10000ffdc`, `0x1000101ec`          |
| The procedure limits phase count to 10 and reports `Exceeded maximum number of update phases (10)`.          | U `0x10000f734`                                      |
| After a phase, the controller refreshes hardware versions and tests the update set again.                    | U `0x100010a30..0x100010b84`                         |

A version mismatch is not proof that the image is older.
The observed equality rule permits a different version to qualify for replacement without an anti-downgrade comparison.
[Verified rule, inferred consequence: U `0x10001c864`, `0x10000fb18..0x10000fb40`]

The installed Ensemble targets are PSoC `1.5.3`, FPGA `0.56.0`, and resources `0.6.0` in hexadecimal-component notation.
The corresponding byte triples are `01 05 03`, `00 56 00`, and `00 06 00`.
The file parser uses radix 16, so FPGA minor `56` means decimal 86.
All three force flags are false.
[Verified: F `ElementsUpdateVersionInfo.plist`, `Ensemble` keys; U `0x10000ede8..0x10000f1d8`, radix constant at `0x10000f1a0`]

The separate `isUpToDate` predicate has weaker absent-value behavior.
An absent hardware version returns true immediately, while an absent file version skips that candidate.
On the first mismatch, it returns the file force flag.
Thus, an up-to-date result alone does not prove that all version reports arrived.
[Verified: U `0x10000e194..0x10000e1fc`]

The updater also checks the installed kext bundle version.
It reads `CFBundleShortVersionString` and applies `hasPrefix` with `0.8`, rather than a numeric minimum-version comparison.
A separate helper invokes `/usr/bin/kextutil` and accepts exit status zero.
Neither helper proves that the complete update path works.
[Verified: U `0x10000643c..0x100006554`, `0x100006558..0x100006734`]

### PSoC file input

The bundled header is `2E12F0690000`, followed by a newline.
It encodes silicon identifier `0x2e12f069`, revision 0, and checksum type 0.
The HAL converts its hexadecimal pairs but retains only the checksum-type field for its bootloader requests.
It does not compare the header silicon identifier or revision with the Enter Bootloader response.
[Verified: F `EnsemblePSoC.cyacd` offsets `0..12`; H `0x87b90..0x87c00`, `0x882d0..0x88314`]

A row has this text layout:

```text
: AA RRRR LLLL DD...DD CC
  array, row number, data length, data, file checksum
```

The row number and length use big-endian byte order in the file.
The HAL converts the row number to little-endian order in bootloader packets.
[Verified: H `0x88450..0x88484`, `0x88744..0x88754`]

| Array | Rows in this file | Data bytes per row | First text offset | Last text offset |
| ----- | ----------------- | -----------------: | ----------------: | ---------------: |
| 1     | 0–255             |                288 |                13 |           150463 |
| 2     | 0–97              |                288 |            151053 |           208283 |
| 3     | 255               |                288 |            208873 |           208873 |

An offline parse of all 355 rows found matching declared lengths and zero byte sums modulo 256, inclusive of each row checksum.
This is an image-file result, not evidence that the HAL performs the same checks.
No array-0 record exists in this file. Consequently, this package alone does not supply that flash array for recovery.
[Verified file coverage: F `EnsemblePSoC.cyacd`, row offsets above]

The HAL parser does not provide a safe substitute for an offline validator:

| Observed behavior                                                                                    | Consequence                                                        | Evidence                                 |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------- |
| It rejects odd text lengths and lengths no greater than six characters.                              | Some malformed rows fail early.                                    | H `0x883c8..0x883dc`                     |
| It calls `strtol` separately for each character without a parse-end check.                           | Invalid hexadecimal characters are not explicitly rejected.        | H `0x88404..0x8844c`                     |
| It logs a declared-length mismatch, then returns true.                                               | That error is not a reliable rejection.                            | H `0x88488..0x884ec`                     |
| It does not precheck the row checksum against the supplied data.                                     | The later device row-checksum comparison carries this check.       | H `0x88398..0x88524`, `0x87eb4..0x87ed8` |
| Its loops lack an input-size bound before stack-buffer writes.                                       | Untrusted oversized text is outside the safe input contract.       | H `0x87b98..0x87bf0`, `0x88400..0x8844c` |
| A non-colon row or parser failure returns through the success path without a failed-progress update. | The property result alone does not prove that a row was processed. | H `0x87e5c..0x87e88`, `0x87e24`          |

### Bootloader session and packets

The HAL first reads the bootloader status, sends `0x60` with selector 0, and waits for status 2.
It opens remote I2C, sleeps three seconds, sends Enter Bootloader, and sleeps another three seconds after the attempt loop.
If the original status was already 2, it first attempts Exit Bootloader.
[Verified: H `0x87c04..0x87cac`, `0x87dcc..0x87e18`]

The packet format is:

```text
Request:  01 command length_lo length_hi payload... checksum_lo checksum_hi 17
Response: 01 status  length_lo length_hi payload... checksum_lo checksum_hi 17
```

The HAL uses a zero status as success.
It checks the start marker, expected payload length, and final marker for the requests below.
It does **not** check the two response checksum bytes.
[Verified: H `0x882e0..0x88314`, `0x88384`, `0x88698..0x886cc`, `0x887e4..0x88814`, `0x88980..0x889dc`, `0x88b68..0x88bc8`]

| Command                  | Request payload                                         | Expected response payload                                             | Evidence             |
| ------------------------ | ------------------------------------------------------- | --------------------------------------------------------------------- | -------------------- |
| `0x38`, Enter Bootloader | Empty                                                   | 8 bytes. The HAL checks length but ignores identity/version contents. | H `0x88240..0x88314` |
| `0x32`, Get Flash Size   | Array byte                                              | 4 bytes, interpreted as first/last row limits                         | H `0x88b08..0x88bc8` |
| `0x37`, Send Data        | 117 data bytes                                          | Empty                                                                 | H `0x88614..0x886cc` |
| `0x39`, Program Row      | Array, row low byte, row high byte, final data fragment | Empty                                                                 | H `0x88728..0x88814` |
| `0x3a`, Verify Row       | Array, row low byte, row high byte                      | One row-checksum byte                                                 | H `0x888d0..0x889dc` |
| `0x3b`, Exit Bootloader  | One zero byte                                           | No response read                                                      | H `0x88320..0x88358` |

For a 288-byte row, the HAL sends two `0x37` packets with 117 data bytes each.
It then sends `0x39` with the final 54 data bytes and the three-byte row address.
The request lengths are 124, 124, and 64 bytes respectively.
[Verified arithmetic and loop: H `0x88620..0x8864c`, `0x88728..0x887c8`]

The HAL uses `0x37` whenever `remaining + 11 >= 129`.
Thus, its final `0x39` data fragment contains at most 117 bytes.
It does not retry a failed Program Row or Verify Row within the row function.
[Verified: H `0x88620..0x8862c`, `0x886ec`, `0x887cc..0x88818`, `0x889e4`]

#### Request checksum

For checksum type 0, the HAL computes:

```text
checksum = (-sum(start marker, command, length bytes, payload)) & 0xffff
```

It transmits the low byte first. The final `0x17` is outside the sum.
For example, Enter Bootloader is `01 38 00 00 c7 ff 17`.
[Verified: H `0x88240..0x8826c`, `0x88c04..0x88c2c`, `0x88c90..0x88c98`]

Type 1 is not a trustworthy alternate cyclic redundancy check (CRC) implementation.
Its inner loop reads the low bit of eight separate bytes, then advances the pointer by eight bytes per requested byte.
It therefore reads `8 * length` bytes rather than the stated `length` bytes.
Its feedback constant has low 16 bits `0x8408`, and it complements and swaps the result.
Do not describe this implementation as a correct standard CRC-16 routine.
[Verified: H `0x88c30..0x88c80`]

The bundled header selects type 0, so that type-1 defect does not affect the observed bundle path.
Unknown nonzero checksum types return zero rather than an explicit error.
[Verified: F header offset 10; H `0x88c04..0x88c10`, `0x88c84..0x88c98`]

#### Row verification and geometry defects

The HAL derives the expected device checksum from the file checksum:

```text
expected = (file_checksum + array + row_lo + row_hi + length_lo + length_hi) & 0xff
```

For a valid file row, that value equals the negative sum of the row data modulo 256.
The HAL compares it with the one-byte `0x3a` response.
This detects many transfer/program errors, but not arbitrary changes with the same byte sum.
[Verified: H `0x87eb4..0x87ed8`, `0x889d0..0x889dc`]

The row-range helper rejects array identifiers above 63.
On the first query, it accepts a structurally valid Get Flash Size response without comparison to the requested row.
It caches the lower and upper limits in a packed value.
On later calls, it masks that value to 16 bits, tests only `last_row >= requested_row`, and overwrites the cache with that truncated value.
It never applies the lower limit in this cached path.
[Verified: H `0x88ad8..0x88b04`, `0x88ba0..0x88bcc`]

Program Row and Verify Row both call this helper.
Thus, verification can reject an out-of-range row only after the first program request already passed the initial geometry query.
The device bootloader can impose further bounds, but its absent implementation remains unknown here.
[Verified call order: H `0x885f8`, `0x88858`; inferred consequence]

### Remote-I2C and kext carrier

The HAL routes miscellaneous requests through IOKit user-client method 5.
A request begins with a 32-bit request kind, followed by a 32-bit value or byte count where applicable.
Write requests append data and round the input allocation to four-byte alignment.
Read requests allocate a four-byte-aligned result buffer and copy the requested byte count back on success.
[Verified: H `0x240b0..0x24288`]

| Operation                   | Miscellaneous request | HAL wrapper | Kext path                    |
| --------------------------- | --------------------: | ----------- | ---------------------------- |
| Open remote I2C             |            0, value 1 | H `0x151c`  | K `0x3d6d..0x3d9b`           |
| Read bytes                  |                     1 | H `0x1578`  | K `0x3da0..0x3dae`, `0x428e` |
| Write bytes                 |                     2 | H `0x15b4`  | K `0x3db3..0x3dc5`, `0x4302` |
| Close remote I2C            |            0, value 0 | H `0x154c`  | K `0x3d6d`, `0x3ffa`         |
| Read PSoC bootloader status |                     3 | H `0x15ec`  | K `0x3dca..0x3e19`           |
| Prepare for update          |      4, Boolean value | H `0x14f0`  | K `0x3e1e`, `0x3fae`         |
| Resume PSoC queue           |            5, value 1 | H `0x14c0`  | K `0x3e35..0x3e52`           |

The numerical request mapping follows the wrapper constants and the kext dispatcher, not the packet command numbers.

The kext uses control register offset `0x18` and data area offset `0x3c00` for this carrier.
Open writes `0x00040000`, then `0x006c0036`. Close writes zero.
The transfer helper ORs `byte_count << 8` into the register, sets bit 30, and uses bit 7 for direction.
The write path clears bit 7. The read path sets bit 7.
[Verified: K `0x3d6d..0x3d9b`, `0x3ffa`, `0x42d9`, `0x434a`, `0x5fa0..0x5ff1`]

The kext byte helpers limit a transfer to 1024 bytes and access the data area in four-byte words.
An excessive size logs an error rather than a structured failure.
The HAL write wrapper sleeps 28000 microseconds after each miscellaneous write request.
[Verified: K `0x428e..0x4383`; H `0x15b4..0x15e8`]

The helper sleeps `floor((9 * byte_count + 9) / 150)` milliseconds before the first completion check.
It then tests busy bit 31 and uses one-millisecond sleeps for up to 1000 polls while that bit remains set.
On timeout, it calls `IOLog`. It produces no structured timeout status.
[Verified: K `0x5ff6..0x607a`, multiplier `0x1b4e81b5` and shift 36]

The read/write dispatcher reaches its common success return after those byte helpers.
The defect is an unpropagated timeout, not suppression of a structured error return.
Therefore, a successful IOKit result does not establish I2C completion.
[Verified: K `0x3da9`, `0x3dc0`, `0x3fb6`, `0x42c6`, `0x4383`, `0x605b..0x607a`]

The HAL generic IOKit helper retries nonzero return codes up to 10000 calls.
It sleeps 200 microseconds only for return code `0xe00002d5`, not for every error.
The unpropagated kext timeout bypasses this retry mechanism because the dispatcher reports success.
[Verified: H `0x2448c..0x244ec`; K `0x3fb6`]

The exact electrical I2C address, clock rate, clock-stretch behavior, and FPGA transfer-engine implementation remain unknown from these host instructions.
The delay formula alone does not establish a measured bus rate.

### FPGA and resource packets

The mailbox wrappers encode:

| Command              | Arguments                                   | Evidence   |
| -------------------- | ------------------------------------------- | ---------- |
| `0x60`, start update | Selector in the low byte                    | H `0x1484` |
| `0x62`, data         | Payload length in a byte, followed by bytes | H `0x14a0` |
| `0x61`, complete     | Selector and extra argument 1               | H `0x1490` |
| `0x63`, restart PSoC | No image payload                            | H `0x14b4` |

The HAL splits binary data into at most 64-byte mailbox payloads.
The final packet carries the remaining byte count, not an obligatory 64-byte pad.
A failed send sets progress to 3. The outer handler can still return true.
[Verified: H `0x87fb0..0x88034`, `0x88110..0x88190`]

The PSoC maps selector 2 to external-flash address `0x1c0000` and selector 1 to `0x380000`.
It accumulates mailbox bytes into a 256-byte buffer and invokes the flash page helper for full pages.
Completion writes any partial final page.
[Verified: P `0x17fb4`, `0x18098`, `0x18198`, `0x183f4`, `0x12444`]

| Image     | Destination interval | Installed image size | Evidence                                             |
| --------- | -------------------- | -------------------: | ---------------------------------------------------- |
| FPGA      | `0x1c0000..0x37ffff` |              1813864 | P `0x18098`, `0x183f4`; F `E2FPGA.bin`               |
| Resources | `0x380000..0x7fffff` |               230036 | P `0x18098`, `0x183f4`; F `EnsembleResourceData.bin` |

The PSoC checks the current page address against the selected interval and records error 2 for an invalid address.
At each 64-KiB boundary, it erases the block before the page write.
These address bounds do not prove that an image is suitable for the hardware.
[Verified: P `0x18098`, `0x1836c`; inferred limit of that check]

The external-flash helper writes a 24-bit address through `0x60800031..0x60800033`.
It uses data window `0x60800c00`, unlock/control register `0x60800034`, and operation/status register `0x6080002e`.
The page helper accepts no more than 256 bytes and issues operation value 10.
The separate erase helper issues operation value 2.
[Verified: P `0x12334`, `0x123e0`, `0x12444`]

The busy helper polls bit 0 with a delay argument of 100 until its accumulated counter reaches 2000000.
The flash helpers record timeout errors, but do not consistently abort every subsequent operation on the first timeout.
The delay unit requires the PSoC clock configuration and is not a measured deadline here.
[Verified: P `0x12370`, `0x123e0`, `0x12444`, delay helper `0x23b18`]

#### Completion checks

The PSoC completion handler uses its saved active selector, flushes the last page, and emits update status.
The command dispatcher does not pass the `0x61` wire selector to that handler.
It computes a CRC-8 over the external-flash bytes through the flash-read helper.
The CRC starts at zero and uses polynomial `0x07`, most-significant bit first.
It is an eight-bit integrity value, not an image signature.
[Verified: P `0x16228`, `0x18198`, `0x124dc`, `0x218cc`, `0x218ec`]

| Update error | Condition                                                        | Evidence                          |
| ------------ | ---------------------------------------------------------------- | --------------------------------- |
| 1            | Unsupported start selector                                       | P `0x17fb4`                       |
| 2            | Current flash address outside the selected interval              | P `0x18098`, `0x18198`, `0x1836c` |
| 3            | Completion while update state is idle sentinel 3                 | P `0x18198`                       |
| 4            | Completion before any full page advanced the destination pointer | P `0x18198`                       |

The completion logic rejects an image shorter than 256 bytes, even if the partial buffer contains data.
It also rejects an exactly full destination interval because the final current address equals the excluded upper bound.
Neither case applies to the installed binary images.
[Verified control flow and arithmetic: P `0x18098`, `0x18198`, `0x1836c`; F image lengths above]

An offline application of that CRC to the complete bundled files gives FPGA `0x2e` and resources `0x1b`.
Those values describe file bytes, not a verified readback from hardware.
[Verified offline calculation: F `E2FPGA.bin`, `EnsembleResourceData.bin`; algorithm P `0x218ec`]

For FPGA, a zero update-result byte sets progress 2 directly. A nonzero result sets progress 3.
For resources, a zero result instead requests persistent property `0x40`, selector 3, and leaves progress at 1.
The resource-version reply stores two version bytes and changes progress from 1 to 2 when the active image selector is 1.
Neither branch compares a reported CRC with a host-computed expected CRC.
The secondary reply does not compare its third data byte with an expected checksum.
[Verified: H `0x81d80..0x81db4`, `0x81e64..0x81e70`, `0x81eac..0x81ed8`]

The resource loader separately requires signature `0x4642`, format version 3, and a header/table CRC-8.
It checks the first 16 header bytes and each eight-byte resource entry against the byte at header offset `0x10`.
This does not cover all resource payload bytes.
[Verified: P `0x1c4f4`; F `EnsembleResourceData.bin` offsets `0..0x13`]

### Errors, time limits, and reconnect

| Layer                      | Observed behavior                                                                                                        | Evidence                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| PSoC bootloader entry      | Up to 1000 status polls with 500-microsecond sleeps, then failure unless status is 2                                     | H `0x87c28..0x87c68`                     |
| Enter Bootloader retry     | Initial attempt, then up to 1000 attempts with five-millisecond sleeps. The terminal counter is also treated as failure. | H `0x87c94..0x87ca0`, `0x87dcc..0x87e04` |
| Exit Bootloader request    | Repeats until the write returns true, with no local bound or delay                                                       | H `0x87cf0..0x87cfc`                     |
| Exit status                | Up to 1000 polls with ten-millisecond sleeps for status 1                                                                | H `0x87d08..0x87d54`                     |
| Application return         | Close I2C, resume the PSoC queue, then up to 1000 ten-millisecond polls for the application report flag                  | H `0x87d58..0x87da4`                     |
| Version refresh after PSoC | Sleep 500 milliseconds, then request persistent property `0x40`, index 0                                                 | H `0x87da8..0x87dc4`                     |
| PSoC row error             | Program or verification failure logs an error and sets progress 3. No row rollback follows.                              | H `0x87ee0..0x87f10`                     |
| App phase wait             | Both timeout getters return 30 seconds. The wait loop distinguishes idle, active, complete, and failed progress.         | U `0x100011f14..0x100012468`             |
| Binary phase start         | The app uses one-second waits and a counter compared with six before it gives up on the start transition.                | U `0x100012c74..0x100012c84`             |
| Procedure bound            | More than ten phases produces the explicit maximum-phase error.                                                          | U `0x10000f734`                          |

These bounds are local loops, not end-to-end guarantees.
The generic IOKit retries and the unbounded Exit Bootloader loop can exceed an app-level expected duration.
A synchronous HAL property call can prevent the app from reaching its next timeout test.
[Inferred from H `0x2448c..0x244ec`, `0x87cf0..0x87cfc`; U `0x100011f24`]

The app defines exactly one required user action: `replugThunderbolt`.
Its controller requests user action between phases, waits for the action handler, then refreshes hardware versions.
The action handler uses offline/online discovery rather than an assumption that the old device reference survives.
[Verified: U reflection `0x100026734`, string `0x100025e50`, controller `0x1000106d4..0x100010b84`, action handler `0x100009880`]

The exact elapsed time for physical reconnect is unknown.
A user-action request is not evidence that a unit with damaged FPGA flash can reenumerate.
[Inferred limit: U `0x100009880`; carrier dependency K `0x5fa0`]

### Checked properties versus assumptions

| Property                   | What the analyzed path establishes                                                  | What it does not establish                                                   |
| -------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Image identity             | Three-byte version equality and bundled filenames. U `0x10000e8bc`, `0x10001c864`   | Cryptographic authenticity, board compatibility, or an anti-downgrade policy |
| PSoC silicon identity      | Enter response has eight payload bytes. H `0x882fc`                                 | Equality with the file silicon identifier or revision                        |
| PSoC row data              | One-byte row-checksum equality. H `0x889d0`                                         | Full byte readback, a collision-resistant digest, or application safety      |
| Bootloader packet response | Start marker, status, expected length, end marker. H `0x88980..0x889cc`             | Response checksum validity                                                   |
| Flash geometry             | Array ID at most 63 and a defective cached upper-row test. H `0x88ad8..0x88b04`     | Correct lower bound or first-row rejection before Program Row                |
| I2C transfer               | Kext polls a busy bit. K `0x6023..0x607a`                                           | Reliable timeout propagation through its caller                              |
| Binary completion          | FPGA needs a zero result. Resources also need a version reply. H `0x81d80..0x81ed8` | Host comparison of all image bytes or their CRC                              |
| Resource structure         | Signature, format version, header/table CRC. P `0x1c4f4`                            | Complete resource payload integrity or semantic validity                     |
| Recovery                   | Host support for a unit whose bootloader status is already 2. H `0x87c80..0x87c94`  | An independent recovery channel or a complete bootloader backup              |

The updater executable also contains an Objective-C `PSoCBootloaderCommunication` class.
It has packet builders, Sync, Enter, Exit, row program, row validation, and checksum methods.
Its existence does not identify the Ensemble image carrier.
The Ensemble path above executes the HAL implementation instead.
[Verified: U `0x100002b54..0x100003924`; Ensemble call chain U `0x10001117c`, `0x10001d508`; H `0x87aa8`]

### Interrupted-update dependencies

The following are dependency inferences, not tested recovery results.

| Interruption                                 | State exposed by the code                                                                                        | Required recovery dependency                                                                                                                                        |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| After PSoC bootloader entry, before all rows | Application rows can be incomplete. The HAL recognizes preexisting bootloader status 2.                          | Intact bootloader, accessible I2C path, compatible FPGA/Thunderbolt carrier, and a host driver that exposes the device. H `0x87c80..0x87c94`, `0x8852c`; K `0x5fa0` |
| During a PSoC row                            | Program Row operates on one row after prior rows already changed. No host rollback exists in the inspected path. | Device bootloader behavior after reset and intact protected/absent regions. H `0x88620..0x889e8`; F row coverage above                                              |
| During external FPGA flash update            | The PSoC writes directly into the selected external-flash interval.                                              | A viable FPGA configuration after reset, or a separately demonstrated physical restoration path. P `0x18098`, `0x12444`, `0x183f4`                                  |
| During resource update                       | Header, table, and payload can belong to different partial versions.                                             | Intact PSoC/FPGA control path and the ability to rewrite the resource interval. P `0x18098`, `0x1c4f4`                                                              |
| After completion but before reconnect        | The app still relies on discovery and a hardware-version refresh.                                                | Reenumeration, a working driver, and reports from the newly active firmware. U `0x1000106d4..0x100010b84`                                                           |
| During an unpropagated remote-I2C timeout    | The host can receive success although the carrier did not complete.                                              | Subsequent bootloader response/row checks must detect the discrepancy. K `0x3da9`, `0x3dc0`, `0x3fb6`; H `0x88980..0x889dc`                                         |

The inspected update handlers do not implement an A/B image transaction, a rollback copy, or an atomic multi-image commit.
That statement is limited to the traced host and PSoC application paths.
An immutable FPGA fallback or other board-level recovery mechanism remains unknown.
[Verified absence within P `0x17fb4..0x183f4`, H `0x87aa8..0x88c98`; unknown hardware behavior]

## Plan

### Close the recovery gaps before an experimental update

- Preserve the absent bootloader and unique device data through an independently authorized backup procedure.
- Establish the physical debug interface, voltage, protection state, and external-flash restoration method.
- Verify recovery without the FPGA image or PSoC application under test.
- Test interrupted updates on a recoverable spare unit, not the only unit.

These are prerequisites, not permission to access hardware.
The package omits array 0, and the host recovery route depends on the remote-I2C carrier.
[Evidence: F row coverage; H `0x87c6c`; K `0x5fa0`]

### Validate candidate files offline

- Reject malformed hexadecimal text, excess lengths, duplicate rows, unexpected arrays, and invalid file checksums before any driver call.
- Compare silicon identity, expected row intervals, image lengths, and hardware versions against an independently established target profile.
- Validate complete resource payloads and FPGA configuration compatibility, not only the vendor completion result.

The vendor parser and completion checks do not supply these guarantees.
[Evidence: H `0x88398..0x884ec`, `0x88ad8..0x88bcc`, `0x81d80..0x81ec8`]
