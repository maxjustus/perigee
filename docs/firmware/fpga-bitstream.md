# Ensemble FPGA bitstream: offline analysis

## Outcome

**Verified:** The copied image matches all 3,944 transport CRC16 checks after bit reversal within each byte.
**Verified:** Mistral disagrees with 192 of 3,856 embedded CRC32 values and reports 12 unresolved clock routes.
**Verified:** Its raw round trip changes 1,152 bytes. Its semantic compiler rejects its own output.
**Unknown:** Hardware acceptance, complete netlist correctness, exact package, speed grade, and safe flash replacement remain unproved.

These results do not authorize a firmware write.
The evidence below separates byte structure, checksum agreement, decoder output, and circuit behavior.

## Scope and terms

- **Verified** means a direct file observation, tool result, or cited source statement. Decoder output alone verifies no circuit behavior.
- **Inferred** means a conclusion from specified evidence.
- **Unknown** means that this analysis cannot establish the claim.
- **FPGA** means field-programmable gate array.
- **RBF** means raw binary configuration file.
- **ORAM**, **PRAM**, and **CRAM** mean option, peripheral, and configuration memory in Mistral.
- **CRC** means cyclic redundancy check. **EDCRC** means the embedded CRC32 for error detection in user mode.
- **HIP** means the hard PCI Express interface. **GPIO** means general-purpose input/output.
- **M10K** means a 10,240-bit memory block. **MLAB** means a logic array block with a memory mode.
- **DSP** means a dedicated arithmetic block here, not the Apogee instruction processor.
- **SCLK** means a sector clock route. **FPLL** means fractional phase-locked loop.
- **SKU** means the complete device order code. **IP** means an intellectual-property core.

All offsets are byte offsets in `E2FPGA.bin`, unless a memory coordinate or source line appears explicitly.
Bit reversal changes each byte, not its address. Normalized-file offsets therefore equal vendor-file offsets.
`work` below means `/tmp/apogee-fw/work-fpga-bitstream`.

**Verified:** This task used files only. It did not invoke hardware tools, the updater, driver clients, or device interfaces.

## Evidence and reference

### Input and tools

| Item | Verified value or evidence |
|---|---|
| Vendor source | `/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/E2FPGA.bin` |
| Analysis copy | `work/E2FPGA.bin` |
| Size | 1,813,864 bytes, `0x1bad68`, 14,510,912 bits |
| SHA-256, original | `b3ef52ae2d1e255307e286d92f2dc92f8dccc06f0f58f7eb1c55a6cbbc4ffdf2` |
| SHA-256, normalized | `d7ad006de7bc0f56295a21e8ceab23e78ec90bcedcacca1f8b4523b5413d2d1f` |
| Decoder | [Project Mistral repository](https://github.com/Ravenslofty/mistral.git), commit `d509238a203aadbb76291ab06543a401df91cf54` |
| Decoder project version | `1.0`, `CMakeLists.txt:3`. Commit date: 2023-09-03 |
| Compiler | Homebrew Clang 22.1.8, target `arm64-apple-darwin27.0.0` |
| Other tools | CMake 4.1.1, Python 3.11.7, XZ/liblzma 5.8.4 |
| Inspector | `scripts/firmware/fpga-bitstream-inspect.py`, Python standard library only |
| Decoder model argument | `5CGXFC3B6F23C7`. This is an analysis hypothesis, not a recovered package identifier |

### Primary sources

| Source | Exact evidence used |
|---|---|
| [Cyclone V Device Datasheet, CV-51002, 2023-05-23](https://docs.altera.com/api/khub/maps/ntTO5vJ6KDUXytXn~tlAoA/attachments/QK3dxcxbO9rXCDOdJ3nW_w-ntTO5vJ6KDUXytXn~tlAoA/content) | Pages 78–79, table 65: uncompressed RBF sizes and the software-version qualification |
| [Cyclone V Device Handbook, 2023-10-18](https://docs.altera.com/api/khub/maps/dvxWxDO1_JfCNh~DgmxAcw/attachments/ozHoJIyPFCMAkmEIi9_Cfw-dvxWxDO1_JfCNh~DgmxAcw/content) | PDF pages 295–296, chapter pages 8-1–8-2: transport CRC16 versus optional user-mode CRC32. Chapter pages 7-45–7-48: security |
| [Quartus Prime Standard and Lite 25.1std release notes, 2025-11-03](https://docs.altera.com/api/khub/maps/DQyuE_ofvGYimhVo5Tsrhw/attachments/izTu9xCTqXCEn4Tc8zQdUQ-DQyuE_ofvGYimhVo5Tsrhw/content) | Pages 3, 11, 14: edition scope, C3 support, device models |
| [Altera FPGA Software Installation and Licensing, 2026-08-31](https://docs.altera.com/api/khub/maps/g0DThssoMSIm~Bd~p5IeuQ/attachments/GXpUO4hP3K04aqrecgy~OA-g0DThssoMSIm~Bd~p5IeuQ/content) | Pages 5, 43, 48: Lite, paid editions, and separate IP licenses |
| [Cyclone V Avalon-MM PCI Express guide, 2026-09-16](https://docs.altera.com/api/khub/maps/yOQp81prLz2Lpuj7oD7GWQ/attachments/o2MoIdYfpiLL6AHU2norhw-yOQp81prLz2Lpuj7oD7GWQ/content) | PDF page 7, printed page 1-2, table 1-2: hard PCIe IP license is free |
| Mistral source at the pinned commit | `libmistral/cv-files.cc:14-38,47-116,119-256`, `cv-opt.cc:165-196`, `cvd-gx25f.cc:18-65` |
| Mistral model and bit databases | `data/models.txt:16-17,197-202,235-248`, `gx25f-pram.txt:153`, `hip-mux.txt:69-122`, `opt-mux.txt:1-15` |

The local copies of these PDFs and their extracted text remain under `work`.
The newer vendor documents establish available tools, not the original Apogee tool version.

### Device inference and exact support

| Status | Conclusion | Evidence |
|---|---|---|
| Verified | The datasheet lists 14,510,912 bits for Cyclone V GX C3 | Datasheet page 79, table 65 |
| Verified | The datasheet qualifies constant uncompressed size by a specific Quartus version | Page 78: “for a specific version” |
| Verified | Mistral supports the `gx25f` die and both `gx25b` and `gx25f` variants | `data/models.txt:16-17` |
| Verified | Its C3 database includes F23, U19, and U15 packages, with multiple grades | `data/models.txt:197-202,235-248` |
| Inferred, high confidence | The image targets the C3/gx25f geometry | Exact size, 85 PRAM frames, 3,856 CRAM frames, every transport CRC16, and coherent PCI identity |
| Inferred, high confidence | The configured HIP favors the PCIe-enabled `5CGXFC3` variant | PRAM identity fields and `models.txt:235-248`, which list `pcie:1` |
| Unknown | Full SKU, package, temperature grade, speed grade, silicon revision | No verified identifier for these properties was recovered |
| Unknown | Exact physical lane count and negotiated PCIe speed | Static HIP fields do not establish link behavior |

Size alone does not identify a package, speed grade, IP implementation, or board revision.
An arbitrary container can match the same byte count.
The frame geometry and checksums provide substantially stronger evidence than the size alone.

`5CGXC3` in the earlier notes is a family/member shorthand, not a complete order code.
The current datasheet places the size table at table 65, not table 63.

### Byte orientation, structure, and compression

**Verified:** Original bytes `0x80..0x83` are `56 56 56 56`.
Mistral emits `6a 6a 6a 6a` at this location (`cv-opt.cc:174-196`).
Each `0x56` becomes `0x6a` after bit reversal within the byte.

**Verified:** The normalized option CRC is `0xfd1a`, stored little-endian at `0x126..0x127`.
The original stores `58 bf`, its per-byte reversal.
Without normalization, the calculated CRC is `0xad98` and the whole option frame has residual `0x0dd0`.
After normalization, its residual is zero.

| Vendor-file range, inclusive | Length | Verified interpretation |
|---|---:|---|
| `0x000000..0x00007f` | 128 | All `ff`, initial fill |
| `0x000080..0x000083` | 4 | Synchronization marker, original `56` repeated |
| `0x000084..0x000123` | 160 | 32 ORAM strips, 40 bits each |
| `0x000124..0x000125` | 2 | Zero bytes |
| `0x000126..0x000127` | 2 | ORAM CRC16 |
| `0x000128..0x000233` | 268 | All `ff`, option-frame fill |
| `0x000234..0x009aef` | 39,100 | 85 PRAM transport frames, 460 bytes each |
| `0x009af0..0x1babaf` | 1,773,760 | 3,856 CRAM transport frames, 460 bytes each |
| `0x1babb0..0x1bac07` | 88 | First postamble, normalized prefix `ec 64`, CRC16 `0xc16e` |
| `0x1bac08..0x1bac13` | 12 | Second postamble, normalized prefix `ae fb`, CRC16 `0x4460` |
| `0x1bac14..0x1bad67` | 340 | All `ff`, final fill |

Source: `cv-files.cc:47-116,119-256`, `cvd-gx25f.cc:21-39`, and direct bytes.
No extra updater envelope remains outside this partition.

**Verified:** ORAM strip 6, bit 35 is one. Mistral calls it `COMPRESSION_DIS`.
Its normalized location is byte `0x110`, mask `0x02`. The original-byte mask is `0x40`.
The uncompressed CRAM extent ends exactly at the first postamble.
Thus this image does not require Mistral's nibble decompressor (`cv-files.cc:76-100`).

**Inferred, high confidence:** This is a clear configuration payload, not an opaque encrypted payload.
The byte structure and directly recovered PCI identity support that conclusion.
**Unknown:** Device key state, tamper protection, or an updater authentication policy cannot be established from this payload.
The handbook describes these features generically. This report does not assert that the unit enables them.

### Integrity layers and round trips

The handbook distinguishes configuration CRC16 from optional error detection in user mode.
See chapter pages 8-1–8-2, PDF pages 295–296.

| Layer | Verified result | Limit |
|---|---|---|
| Original-file SHA-256 | Recorded above and rechecked against the vendor source | A fingerprint, not a vendor signature |
| ORAM CRC16 | 1/1 agreement | Covers `0x84..0x127`, not initial fill |
| PRAM CRC16 | 85/85 agreement | Covers each 460-byte frame |
| CRAM transport CRC16 | 3,856/3,856 agreement | Does not validate circuit semantics |
| Postamble CRC16 | 2/2 agreement | Covers the two command frames |
| Total transport CRC16 | **3,944/3,944 agreement** | No blanket “firmware valid” result |
| Mistral EDCRC32 model | **3,664/3,856 agreement, 192 disagreements** | Includes 1,024 expected-zero columns in four excluded zones |
| Decoder clock routes | **12 unresolved selectors** | Clock connections remain incomplete |
| Semantic compile | **Rejected** at `E2FPGA.lsb.bt:348851` | No regenerated semantic bitstream exists |

CRC16 uses initial state `0xffff`, reflected polynomial `0xa001`, least-significant bit first, and zero residual.
The inspector ports Mistral's separate EDCRC algorithm, initial state one and polynomial `0xf4acfb13`.
It preserves Mistral's excluded zones at columns 318, 1371, 2417, and 3166, each 256 columns wide.

**Verified:** All 192 EDCRC disagreements lie in six groups of 32 columns.
Every original transport CRC16 still agrees in those groups.

| CRAM columns, inclusive | Stored EDCRC XOR model result |
|---|---|
| 757–788 | `0x7912ffc7` |
| 1108–1139 | `0x5f5512bd` |
| 1302–1333 | `0x6b5125ea` |
| 2019–2050 | `0x73bddc50` |
| 2920–2951 | `0x996ce0c7` |
| 3470–3501 | `0xc25ae8f1` |

For column `x`, the transport frame starts at `0x9af0 + 460*x`.
Its EDCRC occupies frame bytes 452–455. Its transport CRC16 occupies bytes 458–459.

**Unknown:** The cause of the EDCRC disagreement is unresolved.
An incomplete mask or memory model is a hypothesis, not proof of a damaged vendor image.
Do not replace the vendor EDCRC with Mistral's values without an independent model.

| Offline experiment | Exit/result | Byte comparison |
|---|---|---|
| Original orientation, `decomp` | Exit 0, **98,083** “Source unknown” warnings | Output is not trustworthy |
| Original orientation, `cycle` | Exit 0. Mistral `diff` output is empty | **25,455 bytes differ**, despite equal sizes |
| Normalized orientation, `decomp` | Exit 0, **12** clock warnings, 349,507 text lines | Partial configuration extraction only |
| Normalized orientation, `cycle` | Exit 0. Mistral `diff` output is empty | **1,152 bytes differ**, despite equal sizes |
| Normalized text, `comp` | Exit 1 | No output file. A subsequent `diff` exits 2 because that file does not exist |

**Verified:** The normalized raw cycle differs only at EDCRC bytes and dependent CRC16 bytes in the 192 columns above.
The first changed offset is `0x5ecf0`. The last is `0x192f97`.
The files are not byte-identical.
Mistral `diff` compares extracted ORAM/PRAM/CRAM state, not all serialized bytes (`cyclonev.cc:366-403`).
Its empty output is therefore not proof of whole-image equivalence.

**Verified:** `rbf_load` does not check CRCs or validate the complete input length (`cv-files.cc:47-116`).
The 98,083-warning experiment demonstrates why decoder exit zero is not a validation test.

### Every normalized-image clock warning

**Verified:** The following is the complete `work/decomp-lsb.log`, in original order:

```text
Source unknown on rnode SCLK.013.009.0014 ( 6, 08)
Source unknown on rnode SCLK.013.000.0020 ( 6, 04)
Source unknown on rnode SCLK.034.000.0005 ( 6, 08)
Source unknown on rnode SCLK.013.009.0022 ( 6, 08)
Source unknown on rnode SCLK.034.000.0009 ( 6, 02)
Source unknown on rnode SCLK.013.009.0029 ( 6, 08)
Source unknown on rnode SCLK.013.000.0012 ( 6, 01)
Source unknown on rnode SCLK.013.009.0000 ( 6, 08)
Source unknown on rnode SCLK.013.009.0025 ( 6, 08)
Source unknown on rnode SCLK.013.000.0025 ( 6, 08)
Source unknown on rnode SCLK.013.009.0028 ( 6, 08)
Source unknown on rnode SCLK.013.000.0015 ( 6, 01)
```

All 12 are unresolved nondefault SCLK source selectors, pattern 6.
They are not transport errors.
Mistral omits each unresolved link from its active-route list (`cv-rmux.cc:185-218`).
The source database lacks a source for each selected input.
The missing connections prevent a complete clock-tree proof.

| Log line | Route node suffix | CRAM selector base `(x,y)` | Database line | Frame offset at base column |
|---:|---|---|---:|---|
| 1 | `013.009.0014` | `(1074,2445)` | 33 | `0x824c8` |
| 2 | `013.000.0020` | `(1074,208)` | 13 | `0x824c8` |
| 3 | `034.000.0005` | `(2768,209)` | 51 | `0x1408b0` |
| 4 | `013.009.0022` | `(1074,1842)` | 41 | `0x824c8` |
| 5 | `034.000.0009` | `(2768,553)` | 55 | `0x1408b0` |
| 6 | `013.009.0029` | `(1074,2444)` | 48 | `0x824c8` |
| 7 | `013.000.0012` | `(1074,468)` | 9 | `0x824c8` |
| 8 | `013.009.0000` | `(1074,1672)` | 19 | `0x824c8` |
| 9 | `013.009.0025` | `(1074,2100)` | 44 | `0x824c8` |
| 10 | `013.000.0025` | `(1074,638)` | 18 | `0x824c8` |
| 11 | `013.009.0028` | `(1074,2358)` | 47 | `0x824c8` |
| 12 | `013.000.0015` | `(1074,640)` | 12 | `0x824c8` |

Database lines refer to `xz -dc mistral/data/gx25f-r.txt.xz`, saved as `work/gx25f-r.txt`.
Selector bases are not entire selector bit extents.

The separate semantic failure is:

```text
E2FPGA.lsb.bt:348851: block mux HSSI.000.011:PCS8G_DIGI_TX_8B10B_ENCODER.0 has unknown choice BMNONE
```

**Verified:** This is an unsupported transceiver mux value, not one of the 12 clock warnings.
No edit removed it, and no warning was suppressed to force a compile.

### Extracted configuration and I/O map

**Verified:** `E2FPGA.lsb.bt` contains 179,186 route records, 170,024 nondefault setting records, and 293 inverter records.
It also contains three option records and the caller-supplied model line.
The three option records are `COMPRESSION_DIS 1`, `JTAG_ID 044ce3e3`, and `OPT_B ffffff40.2cffffff`.
These are decoder names, not recovered RTL signal names.
`JTAG_ID` here is a user option. It is not a measured silicon IDCODE.

**Verified:** The names TSV preserves 1,119 records:
frame regions, all nondefault HIP/GPIO/FPLL/HSSI/PMA3 settings, memory summaries, arithmetic-block summaries, and candidate GPIO pin maps.
Its address column uses file offsets or Mistral coordinates, never invented CPU register addresses.
`Verified decoder output` means exactly that, not verified semantics.

**Verified:** There are 84 GPIO pads with decoded data or output-enable routes.
The route records contain 52 `DATAIN`, 43 `DATAOUT`, and eight `OEIN` endpoints.
A pad can occur in more than one category.
The TSV gives every such pad's candidate F23, U19, and U15 pin from `data/gx25f-pkg.txt`.

| Pad coordinate | Decoded endpoint | F23 candidate | U19 candidate | U15 candidate | Evidence |
|---|---|---|---|---|---|
| `GPIO.003.039.1` | `DATAIN.1` | H6 | G6 | Unbonded | `.bt:134051` |
| `GPIO.003.039.2` | `DATAIN.1` | F7 | E6 | Unbonded | `.bt:109872` |
| `GPIO.008.039.0` | `DATAOUT.0` | E10 | K7 | Unbonded | `.bt:127026` |
| `GPIO.010.039.3` | `DATAOUT.0` | B5 | D7 | C3 | `.bt:75144` |
| `GPIO.013.000.3` | `DATAOUT.0` | AA7 | AA7 | Unbonded | `.bt:135` |
| `GPIO.034.000.0` | `DATAIN.1` | Y17 | W14 | P15 | `.bt:1172` |

**Inferred:** The data routes to pads absent from U15 weaken the U15 package hypothesis.
**Unknown:** No board net name, electrical voltage, relay function, or PSoC bus signal is established by these candidate labels.
Clock-only route records are excluded from the 84-pad count because default clock connections can remain on unused pads.
Dynamic output enables also prevent a static input/output classification.

### Hard PCIe configuration

**Verified:** The identity fields can be recovered directly from PRAM strip 12, independent of the decompiler's text output.
`data/gx25f-pram.txt:153` assigns HIP `001.014` to strip bits 2832–9135.
`data/hip-mux.txt:69-122` defines the function-zero identity fields.

For a HIP-relative bit `k`, use:

```text
b = 9499 - (2832 + k)
offset = 564 + 4 + 1 + 4*b + 8*floor(b/113)
normalized bit = byte[offset] bit 4
original bit   = byte[offset] bit 3
```

The first listed bit of each field is its least-significant bit.
The ranges below contain bits in every fourth byte, not contiguous words.

| Field | Value | HIP-relative bits | Original-file byte range, inclusive |
|---|---|---|---|
| Vendor ID | `0x19c2` | 128–143 | `0x69f1..0x6a2d` |
| Device ID | `0x2201` | 144–159 | `0x69b1..0x69ed` |
| Revision ID | `0x56` | 160–167 | `0x6991..0x69ad` |
| Class code | `0x040100` | 168–191 | `0x6931..0x698d` |
| Subsystem vendor ID | `0x19c2` | 192–207 | `0x68f1..0x692d` |
| Subsystem device ID | `0x2201` | 208–223 | `0x68b1..0x68ed` |

**Inferred, high confidence:** These values identify the Ensemble image.
They agree with the earlier PCI observation in `probe-results.md`, Setup table.
No new PCI access occurred.

| Additional decoder field | Observed value | Confidence and limit |
|---|---|---|
| `BAR0_SIZE_MASK_DATA.0` | `ffff800` | Verified decoder value. A left shift by four gives `ffff8000`, consistent with the earlier 32-KB BAR observation |
| `MAX_PAYLOAD_SIZE.0` | `512` | Verified decoder value, not the current negotiated payload |
| `MSI_SUPPORT.0` | `1` | Verified decoder value, consistent with the earlier MSI observation |
| `MSI_64BIT_ADDRESSING_CAPABLE.0` | `1` | Verified decoder value |
| `MAX_LINK_WIDTH.0`, `LANE_MASK` | `X4`, `X4` | Verified strings only. Do not infer four connected lanes |
| `CORE_CLK_DIVIDER`, `CORE_CLK_SEL` | `16`, `PLD_CLK` | Verified strings only. No clock frequency follows without the missing clock connections |

The TSV preserves all 298 nondefault HIP settings with `.bt` line references.
Slots 1–7 also contain values. Their presence does not prove eight enabled PCI functions.
The inconsistent-looking lane fields and the unresolved transceiver mux need vendor-tool cross-checks.

### Block memory and arithmetic structures

| Structure | Verified decoder result | Limit |
|---|---|---|
| M10K | 135 blocks, every `DISABLE_UNUSED=0` | Decoder configuration, not an independently verified utilization report |
| M10K initial data | 256 raw 40-bit values per block | Logical port/address packing and polarity remain unverified |
| Nonuniform M10K data | 12 blocks | No table was assigned an audio/DSP meaning |
| MLAB | 12 blocks with `RAM_DIS=0` | Contents and logical address maps remain unproved |
| DSP | 39 blocks with nondefault settings out of 57 die locations | 24 retain default `M18X19`, nine decode `M18X19_COMBINED`, six decode `M27X27` |
| FPLL | 41 nondefault settings across configured blocks | Partial clock configuration only |

Source: `.bt` records and Mistral `bels` output.
The TSV cites each block's exact text span and stores each M10K data digest.
Each digest covers 256 five-byte little-endian values in Mistral RAM index order.
This is an extraction format, not a hardware memory layout.

Nonuniform M10K blocks:

| Coordinates | Distinct raw values | First raw value |
|---|---:|---|
| `005.007`, `005.011` | 5 each | `ffffffffff` |
| `018.001` | 256 | `fcccccccef` |
| `033.015`, `033.016`, `033.020`, `033.022` | 65 each | `ffffff53ff` |
| `033.018` | 33 | `ffffffffff` |
| `041.015` | 2 | `ffffffffff` |
| `041.018` | 2 | `fffff0ffff` |
| `041.020` | 2 | `ffffff0fff` |
| `041.021` | 2 | `fffff00fff` |

The 12 MLAB RAM coordinates are:
`008.007`, `008.009`, `008.012`, `014.001`, `014.002`, `017.003`,
`026.003`, `026.008`, `026.010`, `026.011`, `037.012`, and `042.009`.

**Unknown:** The physical memories that implement Apogee code, coefficients, state, mixers, and message slots remain unidentified.
The earlier PSoC evidence identifies their external interfaces, not these physical blocks.
For example, PSoC function `0x13574` writes FPGA code memory through `0x60801c00`.
No proven netlist path connects that address decode to a listed M10K block.

**Unknown:** No HDL, module hierarchy, timing constraints, proprietary DSP IP identity, or complete functional netlist was recovered.
Mistral's README explicitly calls block/port knowledge incomplete.
Its newer DSP documentation still states that the 18×19 configuration is not understood (`docs/cyclonev_details.rst`, DSP section).

## Reproduction

These commands use files only. Run them from the repository root unless a `cd` command changes the directory.
Do not replace the vendor resource with any generated file.

### Fingerprint, normalize, and inspect

```sh
W=/tmp/apogee-fw/work-fpga-bitstream
mkdir -p "$W"
cp '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/E2FPGA.bin' "$W/E2FPGA.bin"
python3 scripts/firmware/fpga-bitstream-inspect.py "$W/E2FPGA.bin" \
  --normalized "$W/E2FPGA.normalized-new.rbf" > "$W/integrity-new.json"
```

The inspector refuses an existing normalized output file.
It reports `transport_crc16_agreement` separately from `mistral_edcrc.agreement`.
Its process exit zero means that the report was produced, not that all checks agree.
The expected values for this image are `true` and `false`, respectively.

**Verified tests:** The CRC16 check vector `123456789` gives `0x4b37`.
The first original CRAM frame passes both checks. A one-bit payload mutation fails both checks.
The report for normalized input matches the original input's checks.
A fresh normalized output matches the expected SHA-256.

```sh
python3 scripts/firmware/fpga-bitstream-test.py \
  /tmp/apogee-fw/work-fpga-bitstream/E2FPGA.bin
```

**Verified:** All six tests passed in 8.822 seconds.
Ruff 0.11.6 accepted both scripts after format normalization.
They cover orientation equivalence, deliberate CRC16 damage, bad lengths, bad headers, normalized output, overwrite refusal, and source-file preservation.
`work/tests.log` retains the complete result.

### Build the pinned decoder

```sh
git clone https://github.com/Ravenslofty/mistral.git "$W/mistral-new"
git -C "$W/mistral-new" checkout d509238a203aadbb76291ab06543a401df91cf54
cmake -S "$W/mistral-new" -B "$W/build-new" -DCMAKE_BUILD_TYPE=Release
cmake --build "$W/build-new" -j 6
```

**Verified:** The unmodified build failed on this Mac at `lzma.h`, then at GNU `ld -r -b binary`.
The successful local configuration was:

```sh
cmake -S "$W/mistral" -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS=-I/opt/homebrew/opt/xz/include \
  -DCMAKE_EXE_LINKER_FLAGS=-L/opt/homebrew/opt/xz/lib
cmake --build "$W/build" -j 6
```

Two commands in the temporary clone's `libmistral/CMakeLists.txt` changed:

```text
ld -r -b binary -o cvd-${die}-r.o ${die}-r.bin
  -> ${PYTHON_EXECUTABLE} /tmp/apogee-fw/work-fpga-bitstream/embed.py ${die}-r.bin cvd-${die}-r.o
ld -r -b binary -o cv-global.o global.bin
  -> ${PYTHON_EXECUTABLE} /tmp/apogee-fw/work-fpga-bitstream/embed.py global.bin cv-global.o
```

The complete temporary helper is:

```python
import pathlib
import subprocess
import sys
name, output = sys.argv[1:]
symbol = '_binary_' + name.replace('-', '_').replace('.', '_')
source = pathlib.Path(output + '.s')
source.write_text(f'.section __DATA,__const\n.balign 16\n.globl _{symbol}_start\n_{symbol}_start:\n.incbin "{name}"\n.globl _{symbol}_end\n_{symbol}_end:\n')
subprocess.run(['clang', '-c', str(source), '-o', output], check=True)
```

This adaptation embeds database bytes in Mach-O objects. It does not change decoder logic or database content.
All source downloads and build products remain under `work`.

### Run and compare

The analysis used the normalized filename `E2FPGA.lsb.rbf`.
For a fresh work directory, use that filename with the inspector's `--normalized` argument.
Keep existing files intact on repeat runs.

```sh
cd "$W"
CV=./build/mistral-cv/mistral-cv
MODEL=5CGXFC3B6F23C7
"$CV" models > models.txt
"$CV" bels "$MODEL" > bels.txt
"$CV" decomp "$MODEL" E2FPGA.bin E2FPGA.bt > decomp.log 2>&1
"$CV" decomp "$MODEL" E2FPGA.lsb.rbf E2FPGA.lsb.bt > decomp-lsb.log 2>&1
"$CV" cycle "$MODEL" E2FPGA.bin cycle.rbf > cycle.log 2>&1
"$CV" diff "$MODEL" E2FPGA.bin cycle.rbf > cycle.diff 2>&1
"$CV" cycle "$MODEL" E2FPGA.lsb.rbf cycle-lsb.rbf > cycle-lsb.log 2>&1
"$CV" diff "$MODEL" E2FPGA.lsb.rbf cycle-lsb.rbf > cycle-lsb.diff 2>&1
cmp E2FPGA.lsb.rbf cycle-lsb.rbf
"$CV" comp E2FPGA.lsb.bt recompiled-lsb.rbf > comp-lsb.log 2>&1
```

The `cmp` and `comp` failures are expected evidence, not instructions to suppress errors.
`work/integrity.json`, `extract-summary.txt`, `M10K.*.json`, and the decoder logs retain the detailed results.

## Modification versus rebuild

### Requirements for a bounded patch

**Inferred requirements from the failures above:**

- Establish the intended field from an independent source, not only a decoder name.
- Preserve all unrelated bytes, unknown selectors, and command frames.
- Resolve the EDCRC model before any change to affected CRAM columns.
- Recompute each applicable transport CRC16 after the final byte change.
- Restore the vendor's per-byte bit orientation after all normalized operations.
- Prove the flash envelope, image selection, recovery path, and power-loss behavior separately.
- Obtain a complete known-good flash backup before any later device experiment.

A HIP identity patch has known PRAM bits and transport CRCs.
It still can prevent driver attachment or host enumeration.
An arithmetic or logic patch needs a proven dependency map, complete clocks, memory semantics, and timing analysis.
This extraction does not provide those proofs.

### Requirements for a source rebuild

| Status | Requirement or tool fact | Evidence |
|---|---|---|
| Verified | Quartus Standard/Lite 25.1std includes C3 support. The listed recommendation is 6 GB RAM | Release notes pages 3 and 11 |
| Verified | The release lists Windows/Linux distributions, not native macOS | Release notes page 3 |
| Verified | Mistral uses the BSD 3-Clause license | Pinned source `LICENSE:1-18` |
| Verified | Quartus Lite needs no paid license or license file | Licensing guide pages 5 and 43 |
| Verified | Standard and Pro use paid licenses | Licensing guide page 43 |
| Verified | Cyclone V hard PCIe IP is free across Avalon-ST, Avalon-MM, and Avalon-MM DMA | PCIe guide page 1-2, table 1-2 |
| Verified | Licensed IP needs its own production license for unrestricted files | Licensing guide page 48 |
| Verified | Evaluation mode can produce a time-limited `.sof` | Licensing guide page 48 |
| Unknown | Original Quartus version, IP revisions, and commercial licenses | The RBF extraction does not recover these |
| Unknown | Exact licenses for the Apogee arithmetic implementation | No recovered IP instance manifest or original project |

**Inferred:** A rebuild needs the full SKU, schematic or verified pin map, oscillator frequencies, reset behavior, voltage constraints, and flash configuration mode.
It also needs RTL or a replacement design, project assignments, timing constraints, memory initialization, and complete IP parameters.
The host/PSoC register contract must remain compatible unless both firmware and driver change.

The vendor hard PCIe core being free does not make Apogee HDL, soft DMA logic, or DSP implementation available.
No vendor source, license grant, or recoverable high-level source follows from a successful bitstream decode.
Mistral exposes configuration data. It is not a substitute for the original Quartus project.

## Safety notes

- Do not flash either Mistral round-trip file. Both differ from their inputs, and the normalized file has 192 unexplained EDCRC changes.
- Do not use decoder exit status as a hardware safety decision. The wrong orientation exits zero with 98,083 warnings.
- Do not assign physical pins from the F23 hypothesis without package evidence. A wrong pin or voltage can damage connected hardware.
- Do not alter key or tamper settings. The handbook describes irreversible protection effects at chapter page 7-48.
- Do not assume encryption or protection is enabled. Their actual state remains unknown.
- Do not overwrite a factory image or its fallback metadata without a verified recovery path.
- Preserve the analog control contract. Earlier PSoC evidence links FPGA control bits to phantom power and analog paths.

The analog warning follows PSoC functions `0x1190c` and `0x14698`, which affect FPGA register `0x0a`, bit 4.
No configuration-bit-to-power-net mapping was established here.

## Proposed tests

These proposals are offline. No device command is proposed at this stage.

| Test | Exact command or prerequisite | Risk |
|---|---|---|
| Independent transport repeat | `python3 scripts/firmware/fpga-bitstream-inspect.py /tmp/apogee-fw/work-fpga-bitstream/E2FPGA.bin` | Read-only, no device risk |
| Byte identity gate | `cmp /tmp/apogee-fw/work-fpga-bitstream/E2FPGA.lsb.rbf /tmp/apogee-fw/work-fpga-bitstream/cycle-lsb.rbf` | Read-only. Expected failure prevents a false equivalence claim |
| EDCRC investigation | Compare the six column groups with small Quartus reference designs for MLAB and block-memory modes | Requires exact reference projects. No device access |
| Package identification | Inspect an existing board photograph or bill of materials for the full package mark | No powered-device access |
| Semantic compile gate | `./build/mistral-cv/mistral-cv comp E2FPGA.lsb.bt recompiled-lsb.rbf` from `work` | File-only. Expected failure at the unsupported HSSI selector |
| Independent vendor rebuild | Obtain the original project, then run its documented synthesis, fit, and timing commands offline | Exact command depends on the unavailable project. Do not substitute an arbitrary top level |

**Unknown:** A safe hardware test command cannot yet be specified from this area's evidence.
The next useful work is the EDCRC model, the 12 clock selectors, the unsupported transceiver mux, and the board pin map.
