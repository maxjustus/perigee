# FPGA reconstruction: checksum model and representation limits

## Outcome

**Verified:** Mistral includes writable MLAB data in its EDCRC calculation. A data-derived zero mask explains every observed EDCRC mismatch.
The same rule matches all 15,424 stored column checks across four vendor images.
No expected CRC constant was changed or skipped to obtain this result.

**Verified:** The raw Mistral cycles preserve every non-checksum byte in these four images.
The independent checksum model restores complete byte identity in memory, but the unmodified Mistral output still differs.

**Verified:** All four semantic compiles still fail at an unrecognized transceiver value.
Their unresolved clock selectors also remain outside the text representation.
A byte-identical raw cycle is not a complete semantic reconstruction or a hardware safety proof.

The first-pass report and scripts remain unchanged.
This pass used copies under `/tmp/apogee-fw/work-fpga-reconstruction`.
No device access, flash operation, updater execution, or commit occurred.

## Evidence conventions and sources

- **Verified** identifies a direct byte observation, source-code fact, or reproducible tool result.
- **Inferred** identifies a conclusion from that evidence.
- **Unknown** identifies a proof gap.
- **EDCRC** means the embedded 32-bit checksum for user-mode error detection.
- **Transport CRC16** means the separate 16-bit checksum of each serialized configuration frame.
- **CRAM** means configuration memory. **PRAM** means peripheral configuration memory.
- **MLAB** means a logic block with a writable memory mode.
- **LUT** means a lookup table. MLAB memory reuses its LUT storage.
- **SCLK** means a sector clock selector in Mistral.
- **HSSI** means the high-speed serial interface block.
- **Raw cycle** means `rbf_load` followed by `rbf_save`.
- **Semantic cycle** means text decompilation followed by text compilation.

`W` below denotes `/tmp/apogee-fw/work-fpga-reconstruction`.
`M` denotes `/tmp/apogee-fw/work-fpga-bitstream/mistral`.
Offsets refer to original `.bin` files. Per-byte bit reversal preserves byte addresses.
A normalized bit number `b` corresponds to original bit number `7-b`.

| Source | Version or exact location |
|---|---|
| [Project Mistral](https://github.com/Ravenslofty/mistral.git) | Commit `d509238a203aadbb76291ab06543a401df91cf54`, dated 2023-09-03 |
| Raw format and checksums | `libmistral/cv-files.cc:14-38,47-116,119-256` |
| Die geometry | `libmistral/cvd-gx25f.cc:7-12,21-55` |
| Tile coordinate conversion | `libmistral/cyclonev.h:1179-1183` |
| MLAB data coordinates | `data/mlab-mux.txt:72,123`, `tools/mux_to_source.py:89-122` |
| Sector clock selector encoding | `libmistral/cv-rpats.cc:67-74,139-146`, `data/gx25f-r.txt.xz` |
| Unknown clock source behavior | `libmistral/cv-rmux.cc:100-121,170-218` |
| Transceiver enum | `data/hssi-mux.txt:169-172`, `data/gx25f-pram.txt:152` |
| Unknown block mux fallback | `libmistral/cv-bmux.cc:381-399` |
| Text output and parser | `mistral-cv/main.cc:359-503,582-804` |
| [Cyclone V Device Handbook, 2023-10-18](https://docs.altera.com/api/khub/maps/dvxWxDO1_JfCNh~DgmxAcw/attachments/ozHoJIyPFCMAkmEIi9_Cfw-dvxWxDO1_JfCNh~DgmxAcw/content) | Chapter pages 8-1–8-2, PDF pages 295–296: separate configuration CRC16 and optional user-mode CRC32 |

**Verified:** The only local Mistral source changes remain the two macOS database-embed commands from the first pass.
`git diff --stat` reports only `libmistral/CMakeLists.txt`, two insertions and two deletions.
No decoder algorithm, bit database, expected checksum, or enum table changed.

Tool versions: Mistral project 1.0 at the commit above, Homebrew Clang 22.1.8, CMake 4.1.1, liblzma 5.8.4, Python 3.11.7.
The new Python comparator reuses the unchanged first-pass CRC primitives.
It derives the additional mask from Mistral geometry and image data.

| New script | SHA-256 after Ruff 0.11.6 format checks |
|---|---|
| `scripts/firmware/fpga-reconstruction-compare.py` | `8d5cd83108bb0d8a64843243042d7ecf338fb1aa6520b33c4ad0481470c9bcc6` |
| `scripts/firmware/fpga-reconstruction-test.py` | `c01d3bea8a2eeb267bcb4260556252a910f9b1a432a5fdaa44e660d7c9d0fc52` |

## Four compatible inputs

Every source file came from:
`/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources`.

**Verified:** All four contain 1,813,864 bytes and the same uncompressed `gx25f` frame geometry.
Each passes all 3,944 transport CRC16 checks after per-byte bit reversal.
Each uses the analysis model argument `5CGXFC3B6F23C7`.
The full physical SKU remains unproved.

| File | SHA-256 of original bytes | Decoded PCI device/revision |
|---|---|---|
| `E2FPGA.bin` | `b3ef52ae2d1e255307e286d92f2dc92f8dccc06f0f58f7eb1c55a6cbbc4ffdf2` | `2201 / 56` |
| `Element2x4_FPGA.bin` | `91ed24529dae10c9327fd7a20d544ad2ebbf89b12588bccb35f6677a299a8fe1` | `2203 / 26` |
| `Element4x6_FPGA.bin` | `0cc43868f1d55dfa9d92b3429f92d2835523ea10eaac546899b6bc722fb53a26` | `2204 / 26` |
| `Element8x8_FPGA.bin` | `36f8c2fc7740a1cf2180be50386b5ddd20308aa5cd1eae38948650711d73fba8` | `2205 / 26` |

PCI vendor `19c2` appears in all four.
These identity bits occupy PRAM strip 12, as documented in `fpga-bitstream.md`.
The Element images provide separate placements and separate stored checksums, not an independent compiler implementation.

## Reproduction of the failure

The initial feedback loop compared the existing Ensemble normalized image with its raw cycle:

```python
from pathlib import Path
p = Path('/tmp/apogee-fw/work-fpga-bitstream')
a = (p / 'E2FPGA.lsb.rbf').read_bytes()
b = (p / 'cycle-lsb.rbf').read_bytes()
assert a == b, 'Reproduction: Mistral raw cycle is not byte-identical'
```

**Verified:** It failed with 1,152 different bytes.
The new four-image runs reproduced that result and found 768 different bytes in each Element cycle.

| Image | Raw-cycle byte differences | Raw-cycle bit differences | EDCRC disagreements | Clock warnings | Semantic compile |
|---|---:|---:|---:|---:|---|
| Ensemble | 1,152 | 4,480 | 192 | 12 | Exit 1 |
| Element 2×4 | 768 | 3,328 | 128 | 8 | Exit 1 |
| Element 4×6 | 768 | 3,072 | 128 | 9 | Exit 1 |
| Element 8×8 | 768 | 2,944 | 128 | 11 | Exit 1 |

**Verified:** Every differing byte is a CRAM frame checksum byte.
No option byte, PRAM payload, CRAM payload, command byte, reserved byte, or postamble byte differs.

## Root cause: omitted writable-data exclusion

### Physical correspondence

Mistral assigns each tile a CRAM base:

```text
base_x = gx25f.x_to_bx[tile_x]
base_y = 2 + 86 * tile_y
```

The MLAB `RAM_DIS` flag occupies relative coordinate `(42,44)`.
A zero flag enables the memory mode according to the database.
The comparator reads this flag directly from the normalized bytes, not from stored EDCRC values.

**Verified:** The raw flags identify exactly the same active-memory tiles as the decoder's `RAM_DIS 0` records.
Ensemble has 12 such tiles. Each Element image has 29.

For each enabled tile, the 640 LUT storage bits occupy:

```text
relative x = 7 through 38
relative y = 1, 6, 9, 14, 17, 22, 25, 30, 32, 38,
             47, 53, 55, 60, 63, 68, 71, 76, 79, 84
```

These coordinates come from `lut_mask` and the ten-cell expansion in `tools/mux_to_source.py`.
The unusual rows 32, 38, 47, and 53 come from its MLAB-specific expansion.
They are not fitted checksum parameters.

**Verified:** The six Ensemble mismatch groups equal the 32 LUT columns of its six memory-bearing tile columns:

| Tile x | CRAM base x | LUT columns | Enabled tile y values |
|---:|---:|---|---|
| 8 | 750 | 757–788 | 7, 9, 12 |
| 14 | 1101 | 1108–1139 | 1, 2 |
| 17 | 1295 | 1302–1333 | 3 |
| 26 | 2012 | 2019–2050 | 3, 8, 10, 11 |
| 37 | 2913 | 2920–2951 | 12 |
| 42 | 3463 | 3470–3501 | 9 |

The Element images move the same structure to four tile columns:

| Image | Tile x 26 | Tile x 34 | Tile x 37 | Tile x 42 |
|---|---|---|---|---|
| 2×4 | 14,15,35 | 10,15,16,22,24,31,32,33,35 | 13,14,15,16,17,18,30,33 | 12,17,18,27,28,30,32,34,35 |
| 4×6 | 20,31,35 | 14,17,20,21,22,23,28,29,31,32,33,34 | 12,19,20,29,30,31 | 14,16,18,26,28,29,32,33 |
| 8×8 | 30,35 | 15,26,30,31,32,34,35 | 15,16,17,19,25,27,28,29,30,31,35 | 11,16,17,18,23,29,31,34,35 |

Each cell lists enabled tile y values.
Tile column 34 has CRAM base 2714 and LUT columns 2721–2752.
The other three column ranges equal their Ensemble ranges.

### Exact checksum calculation

For this die, CRAM frame `x` starts at byte `39664 + 460*x`.
For CRAM coordinate `(x,y)`, its bit position within that frame is:

```text
q = y - 20
frame_bit = 224 + (31 XOR floor(q/106)) + 32*(q mod 106)
file_byte = 39664 + 460*x + floor(frame_bit/8)
normalized_bit = frame_bit mod 8
original_bit = 7 - normalized_bit
```

This comes from `rbf_load` and `rbf_save`, with the `gx25f` dimensions 3856×3412.
The subtraction by 20 comes from the existing frame padding calculation.

**Verified Mistral algorithm:** `crc32` starts with accumulator one and polynomial `0xf4acfb13`.
It processes payload bits through 106 words, with word-bit index 31 down to zero as the outer loop.
It reads frame bytes 28–451.
It excludes the command prefix, the stored EDCRC, and the transport CRC16.

**Verified omission:** `crc32(const uint8_t *src)` receives no column or MLAB state.
It cannot exclude writable LUT storage by itself.
`rbf_save` only applies whole-column exclusions from `noedcrc_zones`.

The additional rule tested here is:

1. Read `RAM_DIS` for every physical MLAB tile.
2. If the flag is zero, locate its 640 LUT storage bits.
3. Force those bits to zero in a temporary checksum input.
4. Apply the unchanged Mistral CRC32 algorithm to that temporary input.
5. Keep the serialized payload unchanged.

The comparator retains the existing four 256-column exclusions at 318, 1371, 2417, and 3166.
Those 1,024 columns store zero EDCRC values and already agree with Mistral.
The new mask does not overlap those exclusions.

**Verified:** The resulting EDCRC agrees with every stored value in all four images.
Of the 15,424 column checks, 4,096 are expected-zero checks from the existing exclusions.
The other 11,328 are computed CRC32 agreements.

**Unknown:** The proprietary vendor CRC implementation was not available for source comparison.
The vendor handbook establishes the two integrity layers, but does not specify this bit-level exclusion rule.
The vendor-generated images provide the independent expected checksums.
The rule is therefore an evidence-backed reconstruction, not a quoted vendor algorithm.

### Negative controls

| Test | Verified result | Consequence |
|---|---|---|
| Unchanged Mistral algorithm | 192 Ensemble and 128 per Element disagreements | Reproduces the defect |
| Zero only enabled MLAB LUT storage | Zero disagreements across all four images | Explains all affected columns |
| Force those bits to one | 192 Ensemble and 128 per Element disagreements remain | Rejects the opposite mask polarity |
| Zero LUT storage in all 291 MLAB tiles | 288/288 selected columns disagree in every image | Rejects a blanket MLAB-column exclusion |
| Toggle one enabled-memory data bit | Unmasked CRC changes, masked CRC does not | The rule excludes data, not the entire frame |
| Toggle one unmasked payload bit in that frame | Masked CRC changes | The remaining frame data still participates |
| Recompute from raw-cycle bytes and their own RAM flags | Exact original bytes after checksum replacement in memory | No expected checksum is copied from the original |

The last comparison is an internal diagnostic. The script writes no reconstructed image.

| Image | Excluded writable bits | Bits that are one in the input | Bits that are already zero |
|---|---:|---:|---:|
| Ensemble | 7,680 | 6,336 | 1,344 |
| Each Element variant | 18,560 | 15,232 | 3,328 |

The mask is not equivalent to a constant EDCRC correction.
It depends on tile mode, tile location, and each stored LUT bit.
The synthetic mutation tests also exercise that distinction.

### Exact different checksum bits

The original raw cycles differ at frame-relative bytes 452–455 and 458–459 only.
Bytes 452–455 store EDCRC, little-endian.
Bytes 458–459 store transport CRC16, little-endian.

For every column in each row below, XOR the normalized original checksum with the raw-cycle checksum to obtain the listed value.
Each row covers exactly 32 columns.
These are measured deltas, not constants used by the model.

| Image | Columns | EDCRC XOR | CRC16 XOR |
|---|---|---|---|
| Ensemble | 757–788 | `7912ffc7` | `02d0` |
| Ensemble | 1108–1139 | `5f5512bd` | `f082` |
| Ensemble | 1302–1333 | `6b5125ea` | `2d3a` |
| Ensemble | 2019–2050 | `73bddc50` | `3408` |
| Ensemble | 2920–2951 | `996ce0c7` | `1e5c` |
| Ensemble | 3470–3501 | `c25ae8f1` | `12c6` |
| Element 2×4 | 2019–2050 | `48aae38a` | `727b` |
| Element 2×4 | 2721–2752 | `cfcff033` | `fd4a` |
| Element 2×4 | 2920–2951 | `fe2d99e5` | `b562` |
| Element 2×4 | 3470–3501 | `acc5513d` | `cc05` |
| Element 4×6 | 2019–2050 | `b2bf4d6d` | `40a1` |
| Element 4×6 | 2721–2752 | `1f292bdb` | `770f` |
| Element 4×6 | 2920–2951 | `0a072942` | `9273` |
| Element 4×6 | 3470–3501 | `5f674505` | `fce2` |
| Element 8×8 | 2019–2050 | `4198659b` | `572f` |
| Element 8×8 | 2721–2752 | `4a92bc58` | `ad51` |
| Element 8×8 | 2920–2951 | `62b4c848` | `7668` |
| Element 8×8 | 3470–3501 | `ffc340d9` | `b21e` |

These values and the frame formula specify every changed checksum bit exactly.
Per-byte bit reversal gives the corresponding changes in vendor orientation.
The altered EDCRC participates in CRC16, which explains the dependent CRC16 changes.
There is no second unexplained transport-CRC defect.

**Verified:** The option that Mistral names `CRC_ERROR_DETECTION_EN` is zero in all four inputs.
It occupies option strip 2, bit 13, original byte `0xb8`, bit 2.
This does not explain away the checksum-model defect: the vendor still stores the nonzero column checks that the corrected model predicts.
The option does not establish the later runtime state of the unit.

## Separate semantic representation defects

### Transceiver `BMNONE`

**Verified:** All four files contain raw value three for:

```text
HSSI.000.011:PCS8G_DIGI_TX_8B10B_ENCODER.0
```

The field occupies PRAM strip 12, bits 2030 and 2031.
Those bits are original-file locations `0x78fd:3` and `0x78f9:3`, respectively.
Both are one in all four images.
They lie in PRAM transport frame 66, whose start is `0x78cc`.

Mistral's enum defines only:

```text
0 off
1 ibm
2 sgx
```

`bmux_m_read` returns `BMNONE` when no entry matches.
The decompiler prints that sentinel without the original numeric value.
The compiler then rejects the sentinel instead of restoring the two bits.
This is an enum/representation gap, not an EDCRC error.

| Image | Exact failing text line | Exit |
|---|---:|---:|
| `E2FPGA.bin.bt` | 348851 | 1 |
| `Element2x4_FPGA.bin.bt` | 362178 | 1 |
| `Element4x6_FPGA.bin.bt` | 363593 | 1 |
| `Element8x8_FPGA.bin.bt` | 361403 | 1 |

Every log contains the same failure suffix:

```text
block mux HSSI.000.011:PCS8G_DIGI_TX_8B10B_ENCODER.0 has unknown choice BMNONE
```

**Unknown:** The hardware meaning of value three remains unresolved.
No replacement with `off`, `ibm`, or `sgx` was attempted.
No enum alias was added to force compilation.
The raw cycle preserves both bits already.

### Twelve sector-clock selectors

**Verified:** All warnings use Mistral pattern 6, a five-bit one-hot selector.
Its valid raw masks are `01`, `02`, `04`, `08`, and `10`.
For each warning, the selected source slot is absent from that node's source database.
The masks themselves are recognized pattern values.

These selectors occupy CRAM columns 1074–1078 or 2768–2772.
Neither range overlaps any EDCRC mismatch group in any image.
The mask correction does not alter these selectors.

The table lists raw values in Ensemble, Element 2×4, Element 4×6, and Element 8×8 order.
An asterisk identifies a missing source slot and therefore a warning.

| SCLK suffix | E2 | 2×4 | 4×6 | 8×8 | First original byte / bit |
|---|---|---|---|---|---|
| `013.000.0012` | `01*` | `01*` | `01*` | `01*` | `0x82547 / 4` |
| `013.000.0015` | `01*` | `02` | `02` | `08` | `0x8264f / 5` |
| `013.000.0020` | `04*` | `04*` | `01` | `04*` | `0x8262f / 1` |
| `013.000.0025` | `08*` | `01` | `08*` | `08*` | `0x82647 / 5` |
| `013.009.0000` | `08*` | `08*` | `08*` | `08*` | `0x825de / 7` |
| `013.009.0014` | `08*` | `08*` | `08*` | `08*` | `0x82659 / 6` |
| `013.009.0022` | `08*` | `02` | `08*` | `08*` | `0x82535 / 1` |
| `013.009.0025` | `08*` | `08*` | `08*` | `08*` | `0x825ed / 3` |
| `013.009.0028` | `08*` | `08*` | `08*` | `08*` | `0x824fd / 6` |
| `013.009.0029` | `08*` | `08*` | `08*` | `08*` | `0x82655 / 6` |
| `034.000.0005` | `08*` | `08*` | `08*` | `08*` | `0x140a1b / 1` |
| `034.000.0009` | `02*` | `08` | `08` | `02*` | `0x1408db / 5` |

For selector bit index `i=0..4`, add `460*i` to the listed byte address.
The original bit number stays unchanged.
This defines the complete raw field, not only its first bit.
`W/selector-scope.json` retains all five addresses and the database source entries.

**Verified:** None of the warned nodes appears as a source in its image's decoded active-route records.
Mistral's fixed-route activity test consults downstream selectors (`cv-rmux.cc:170-183`).
An unknown upstream selector does not, by itself, force those downstream selectors inactive.

**Inferred:** These warnings can concern unused clock paths rather than missing clocks in active logic.
**Unknown:** The incomplete route database prevents a proof that the hardware never consumes them.
They still prevent a claim that the semantic text preserves every configuration selector.

The raw cycle retains every selector bit.
The semantic decompiler emits no source-selection directive for unresolved links (`cv-rmux.cc:199-214`).
This separates text information loss from the raw checksum-model defect.

## Hypotheses: confirmed and refuted

| Hypothesis | Result | Evidence |
|---|---|---|
| Writable MLAB data needs an EDCRC exclusion | Confirmed for these four images | Direct RAM flags and LUT coordinates predict every stored CRC32 |
| The six groups identify six damaged areas in the vendor file | Refuted as an explanation of the observed discrepancy | All transport checks agree. The data-derived rule predicts every checksum without payload changes |
| Raw `rbf_load` loses data in the affected columns | Refuted for these fixtures | Every non-checksum byte survives every raw cycle |
| A global polynomial, seed, or bit-order error causes the mismatch | Refuted for these fixtures | The unchanged primitive agrees everywhere once mode-dependent data is zeroed for the calculation |
| An entire MLAB tile column must be excluded | Refuted | The blanket mask fails 288/288 tested columns per image |
| HSSI `BMNONE` causes the EDCRC differences | Refuted | The unknown value lies in preserved PRAM bits. EDCRC covers CRAM |
| The unresolved clock selectors cause those differences | Refuted | Selector columns do not overlap. All raw selector bits survive unchanged |
| Complete semantic reconstruction now works | Refuted | All four text compiles still fail at the unrecognized HSSI value |

“Refuted for these fixtures” is not a universal claim about every Cyclone V image or every loader path.

## Reproducible commands

### Copy, normalize, and run the unchanged decoder

Run from the repository root.
Use the first-pass decoder build. It contains no checksum or enum modifications.

```sh
W=/tmp/apogee-fw/work-fpga-reconstruction
M=/tmp/apogee-fw/work-fpga-bitstream/mistral
CV=/tmp/apogee-fw/work-fpga-bitstream/build/mistral-cv/mistral-cv
mkdir -p "$W"
python3 - <<'PY'
from pathlib import Path
src = Path('/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources')
dst = Path('/tmp/apogee-fw/work-fpga-reconstruction')
names = ['E2FPGA.bin', 'Element2x4_FPGA.bin', 'Element4x6_FPGA.bin', 'Element8x8_FPGA.bin']
reverse = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))
for name in names:
    data = (src / name).read_bytes()
    (dst / name).write_bytes(data)
    (dst / (name + '.rbf')).write_bytes(data.translate(reverse))
PY
for f in E2FPGA.bin Element2x4_FPGA.bin Element4x6_FPGA.bin Element8x8_FPGA.bin; do
  "$CV" decomp 5CGXFC3B6F23C7 "$W/$f.rbf" "$W/$f.bt" > "$W/$f.decomp.log" 2>&1
  "$CV" cycle 5CGXFC3B6F23C7 "$W/$f.rbf" "$W/$f.cycle.rbf" > "$W/$f.cycle.log" 2>&1
  "$CV" comp "$W/$f.bt" "$W/$f.semantic.rbf" > "$W/$f.comp.log" 2>&1
  printf '%s semantic_exit=%s\n' "$f" "$?"
done
```

The semantic compile exits are one. No `.semantic.rbf` files result.
The source-copy commands only replace files under the dedicated temporary directory.

### Compare every checksum and byte

```sh
python3 scripts/firmware/fpga-reconstruction-compare.py "$W" \
  --source "$M" > "$W/comparison.json"
```

Expected report fields for each image:

```text
transport_frames: 3944
bad_transport: []
raw_cycle_nonchecksum_offsets: []
zero_mask_bad_columns: []
model_cycle_byte_identical: true
```

`unmasked_bad_columns` retains every upstream mismatch.
`one_mask_bad_columns` retains the failed opposite-polarity control.
`groups` contains the exact checksum XOR deltas above.
The comparator performs the final byte comparison in memory and writes JSON only.
It does not modify any input or export a flashable file.

### Regression tests

```sh
python3 scripts/firmware/fpga-reconstruction-test.py "$W" "$M"
ruff check --no-cache scripts/firmware/fpga-reconstruction-compare.py \
  scripts/firmware/fpga-reconstruction-test.py
```

**Verified:** Before the mask implementation, three test methods produced eight failing image subtests.
The checksum-agreement test and writable-data mutation test each failed on all four images.
The geometry test passed.
`W/tests-red.log` retains that result.

**Verified:** After the mask implementation, all three test methods passed across the four images.
The tests also verify unchanged input bytes and a changed CRC for an unmasked payload mutation.
`W/tests-green.log` retains the result: three methods passed in 18.659 seconds.
The unchanged first-pass suite also passed all six methods in 8.814 seconds.
`W/first-pass-tests.log` retains that result.
Ruff 0.11.6 accepted both new scripts.
The expected checksums come from the vendor files, not fitted constants in the tests.

## Limits and next proof requirements

**Verified scope of the correction:** This pass adds an independent file-only CRC model and regression tests.
It does not patch Mistral, the first-pass inspector, or the first-pass report.
The original inspector intentionally continues to report the original Mistral EDCRC disagreements.

**Inferred implementation requirement:** A Mistral correction needs tile/column context when it computes EDCRC.
It must zero writable LUT data only in the checksum input.
It must retain that data in the serialized payload and then recompute transport CRC16 normally.
Zeroed output payload is not an acceptable substitute.

**Unknown:** The rule's coverage for other dies, ROM-only modes, unusual memory packing, partial configuration, and different Quartus versions needs reference images.
The four fixtures do not contain every possible configuration.
The mutation tests establish model behavior, not hardware behavior.

**Unknown:** The meaning of transceiver raw value three and the absent SCLK source slots still need independent documentation or reference designs.
A text format with an explicit raw fallback can preserve unknown bits without a false semantic name.
That requires separate round-trip tests. This pass does not implement such a fallback.

**Unknown:** Other losses after the first semantic compile error remain unmeasured.
No forced compile bypassed that error, so this report does not claim that it is the only semantic defect.

## Safety notes

Do not flash raw-cycle files or a future model-derived file on the strength of this analysis.
Checksum agreement and byte identity do not prove pin assignments, clock correctness, runtime behavior, updater integrity, or recovery safety.

The twelve clock warnings and the HSSI failure remain visible.
The fixed checksum model is not permission to suppress them.
No hardware command is proposed until the semantic and recovery proof gaps are addressed.
