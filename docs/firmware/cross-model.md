# Cross-model firmware comparison

The Element and Ensemble firmware images are separate builds. They share a
small verbatim core of library functions and nothing else at the byte level.

## Outcome

| Measurement | Value |
|---|---|
| Ensemble application | 90,624 bytes, 354 rows |
| Element application | 48,128 bytes, 188 rows |
| Silicon header, both files | `2E12F0690000`, additive checksum |
| Bootloader boundary, both files | Row 255, a 64 KB region |
| Overlapping rows byte-identical | 0 of 188 |
| Identical bytes in the overlap | 2,902 of 54,144, about 5 percent |
| Ensemble functions identical at the same address | 1 of 666 |
| Ensemble function bodies found verbatim at other addresses | 132 |
| Changed bytes outside mapped function bodies | 65,280 |

The one same-address match is the C runtime stub at `0x1003C`, a frame-dummy
no-op. It is identical because it does almost nothing.

## What the shared core contains

The 132 verbatim bodies are the library layer. Representative members,
with their Ensemble and Element addresses:

| Function | Ensemble | Element |
|---|---|---|
| `FlashBridge_SetAddress24` | `0x12334` | `0x1543C` |
| `FlashBridge_Erase` | `0x12444` | `0x1554C` |
| `FlashBridge_Program` | `0x124A4` | `0x155AC` |
| `FPGA_WriteWord32LE` | `0x12610` | `0x15698` |
| `ProtocolSerializeBlock` | `0x15B48` | `0x10D38` |
| `SchedulerAddTimer` | `0x2019C` | `0x170B8` |
| `SchedulerRemoveTimer` | `0x20230` | `0x1714C` |
| `EepromStreamFlush` | `0x1318C` | `0x158B0` |
| `DSP_InitProtocolState` | `0x13294` | `0x166D8` |

Everything else differs: the dispatcher tables, every mapped subsystem
function, the version constants, and the full application layout. The
Element build is version 0.5 and the Ensemble build is 1.5.3, so the
source generations also differ.

## Consequences

- The Element firmware is not a second source for the Ensemble. A
  replacement image must derive from the Ensemble baseline alone.
- The shared core confirms the layering: hardware access, flash bridge,
  protocol serialization, and the scheduler are stable vendor library
  code. The product logic above them changed completely.
- The 132-body count is a lower bound. A function whose literal pool
  moved, or whose constants changed, does not match exactly even when
  its logic is the same.
- The FPGA images tell the same story from the first reconstruction pass:
  same die, same frame geometry, different placements and checksums.

## Method and limits

`scripts/firmware/cross-model-compare.py` parses both CYACD files, diffs
the overlapping rows, compares each mapped Ensemble function over its
full byte range, and searches the Element image for each body verbatim.
Bodies that are mostly `0xFF` padding are excluded from the relocation
search, because erased flash matches everywhere.

The test suite covers parsing, row classification, disjoint ranges,
function slicing, and the vendor files. Six tests.

```sh
python3 scripts/firmware/cross-model-compare-test.py -v
python3 scripts/firmware/cross-model-compare.py
```

No device access. Both files come from the installed updater bundle,
hashes in `docs/firmware/provenance.json`.
