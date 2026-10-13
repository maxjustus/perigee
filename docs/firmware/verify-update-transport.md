# Independent verification of the update transport

The original binaries confirm the transport and checksum defects, but two claims need narrower descriptions.
The kernel does not return a structured timeout error, and resource completion needs a later version reply.

## Scope and evidence

This review used static analysis only. No device interface, updater process, driver load, or flash operation ran.
The shared brief supplied paths, not evidence. This review did not use `docs/firmware/updater.md` or its temporary artifacts.

Terms:

- **HAL**: the vendor hardware abstraction layer plugin for Core Audio.
- **Kext**: the vendor kernel extension.
- **PSoC**: the Cypress programmable system-on-chip microcontroller.
- **FPGA**: the field-programmable gate array.
- **CRC**: cyclic redundancy check.
- **Remote I2C**: the vendor interface to the serial bus through the FPGA.
- **Verified**: direct instruction or data evidence.
- **Inferred**: a consequence of that evidence, not an observed device result.
- **Unknown**: a question that these artifacts do not settle.

All HAL addresses refer to its **arm64** slice. All kext addresses refer to its **x86_64** slice.
Updater addresses refer to its **arm64** slice. PSoC addresses refer to its reconstructed Thumb instruction bytes.
These addresses do not prove which slices the current host executes.

### Original artifacts

| Artifact | Original path | Slice base in universal file | SHA-256 of examined slice |
|---|---|---:|---|
| HAL | `/Library/Audio/Plug-Ins/HAL-disabled/ApogeeElementEnsemble.driver/Contents/MacOS/ApogeeElementEnsemble` | `0x1a4000` | `f6c057b0bbda413c111b3cd9ee92c327a410736dc8fef21252cd8e1a8559f4c1` |
| Kext | `/Library/Extensions/ApogeeElementEnsemble.kext/Contents/MacOS/ApogeeElementEnsemble` | `0x1000` | `4e6c613a454ce9c6b337b3647677d06300757c452c92b408f9d5d97a29ea7b01` |
| Updater | `/Applications/Utilities/Apogee Firmware Updater.app/Contents/MacOS/Apogee Firmware Updater` | `0xb0000` | `4ca75e9f41bf873696835a23d9cc5ce16d123fe79f3d429da60e1bd5600f3bd4` |

For cited HAL and kext text addresses, file offset equals slice base plus address.
For cited updater addresses, subtract `0x100000000`, then add its slice base.

The original resource `EnsemblePSoC.cyacd` has SHA-256 `7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24`.
Its path is the updater bundle's `Contents/Resources/EnsemblePSoC.cyacd`.
Its 355 rows each contain 288 data bytes. Every row passes its additive record checksum.

For PSoC reconstruction, each row maps to `array * 0x10000 + row * 256`.
The first 256 data bytes supply flash bytes. The last 32 supply configuration bytes, not subsequent instructions.
The reconstructed application matched `/tmp/apogee-fw/flash.bin` byte for byte.
The decompiler supplied candidate PSoC addresses only. Capstone decoded those candidates from the original resource's reconstructed bytes.
LLVM decoded the original host executables. Raw table bytes independently resolved indirect branches.

## Verdicts

| Claim | Verdict | Necessary qualification |
|---|---|---|
| PSoC uses remote I2C, FPGA/resource use `0x60/0x62/0x61` | **Confirmed** | PSoC also uses `0x60`, selector zero, to enter the bootloader. Only `0x60/0x61` carry firmware selectors. |
| HAL ignores response checksums and silicon identity | **Confirmed** | This means packet trailer checksums. HAL does compare the separate one-byte row checksum. |
| Kext discards a returned remote-I2C timeout status | **Refuted as stated** | The transfer helper logs the timeout without a structured error return. The dispatcher nevertheless returns success. |
| HAL accepts external completion without a device-CRC comparison | **Confirmed** | FPGA completion is direct. Resource completion waits for a version reply, also without a CRC comparison. |
| CRC type one reads `8 * length`, while the bundle uses type zero | **Confirmed** | The 968-byte read requires earlier protocol operations to succeed. The stock bundle does not select that branch. |

## PSoC and external-image transport

**Verified.** The updater's PSoC controller submits a firmware packet through a protocol method at `0x100011980–0x100011998`.
The original protocol witness table at `0x100028940 + 0x28` points to `0x10001ddc8`.
That witness loads the device method at class offset `0x1c8` (`0x10001dddc`).
For `EnsembleSubDevice`, metadata at `0x1000308a0 + 0x1c8` contains `0x10001d4b8`.
This method constructs Core Audio selector `0x41454655`, or `AEFU`, at `0x10001d508–0x10001d514`.
It supplies an eight-byte property-list reference to `AudioObjectSetPropertyData` at `0x10001d5cc–0x10001d5d0`.
The mere presence of the updater's separate `PSoCBootloaderCommunication` class does not establish the Ensemble transport.

**Verified caller constraints.** HAL property entry `0x84248` requires size eight and a non-null data pointer (`0x84268–0x84274`).
Selector `AEFU` branches to `0x84dd8` through `0x848d0–0x848dc`.
The property element must be 1, 2, or 3. HAL subtracts one and extracts a data object (`0x84dd8–0x84e24`).
It calls `_updateFirmware(type, bytes, length)` at `0x84e34`.
That function dispatches type zero to PSoC, one to resource data, and two to FPGA (`0x85308–0x85378`).

| Image | Start | Data | End |
|---|---|---|---|
| PSoC | `0x87c20–0x87c24`: `0x60`, selector 0. Then remote-I2C open and bootloader entry. | `0x87e84`, `0x87eac`, `0x87ed8`: parse, program, verify each row. | Zero-length submission calls bootloader exit at `0x87cf8`. |
| Resource | `0x87f6c–0x87f70`: selector 1. | `0x87fb4–0x87ff0`: packets of at most 64 bytes. | `0x88000–0x88004`: selector 1. |
| FPGA | `0x880c4–0x880c8`: selector 2. | `0x88114–0x88150`: packets of at most 64 bytes. | `0x8815c–0x88160`: selector 2. |

The original wrappers establish the command bytes:

```text
HAL 0x1484  22 1c 00 12  and w2, w1, #0xff
HAL 0x1488  01 0c 80 52  mov w1, #0x60
HAL 0x1494  21 0c 80 52  mov w1, #0x61
HAL 0x1498  23 00 80 52  mov w3, #1
HAL 0x14a4  42 1c 00 12  and w2, w2, #0xff
HAL 0x14a8  41 0c 80 52  mov w1, #0x62
HAL 0x14ac  e3 03 02 aa  mov x3, x2
HAL 0x1580  21 00 80 52  mov w1, #1
HAL 0x15c8  41 00 80 52  mov w1, #2
```

`0x14a4` masks the packet length, not a firmware selector.
`0x1580` and `0x15c8` select miscellaneous read and write requests.
HAL packages both as kernel method five at `0x24200` and `0x2427c`.

**Verified state constraints.** PSoC start accepts HAL state 0, 2, or 3 (`0x87ae0–0x87af8`).
It requires a header of at least 12 characters (`0x87bf4–0x87bfc`).
It then requires bootloader status two and a successful remote-I2C open (`0x87c28–0x87c74`).
Bootloader entry runs at `0x87c9c`, with retry calls at `0x87de4`.
The row path requires state one, active type zero, nonzero length, and an initial colon (`0x87cc8–0x87cd0`, `0x87e5c–0x87e64`).
External data paths require state one and their respective active type (`0x87f84–0x87f94`, `0x880e4–0x880f4`).
Their zero-length end paths precede those type checks.

**Inferred safety consequence.** The external-image protocol is not a substitute for the PSoC bootloader protocol.
The numeric address interval `0x87aa8–0x88c98` also contains the resource and FPGA methods, not only PSoC code.

## Response integrity and silicon identity

**Verified.** HAL converts header characters to halfwords at `0x87ba8–0x87bf0`.
Only decoded header item five supplies persistent state:

```text
HAL 0x87bfc  e8 67 40 79  ldrh w8, [sp, #0x32]
HAL 0x87c00  68 a2 06 b9  str w8, [x19, #0x6a0]
```

The first four decoded bytes and the revision byte do not enter an identity comparison in this function.
The bootloader-entry reply supplies eight payload bytes, but HAL does not read any of them:

```text
HAL 0x882d8  e2 01 80 52  mov w2, #15
HAL 0x882dc  a7 e4 fd 97  bl readDataFromRemoteI2C
HAL 0x882e8  e9 07 40 39  ldrb w9, [sp, #1]
HAL 0x882ec  49 01 00 35  cbnz w9, 0x88314
HAL 0x882f0  e9 03 40 39  ldrb w9, [sp]
HAL 0x882f4  3f 05 00 71  cmp w9, #1
HAL 0x882fc  e8 0b 40 39  ldrb w8, [sp, #2]
HAL 0x88300  1f 21 00 71  cmp w8, #8
HAL 0x88308  e8 0f 40 39  ldrb w8, [sp, #3]
HAL 0x88384  e8 3b 40 39  ldrb w8, [sp, #14]
HAL 0x88388  1f 5d 00 71  cmp w8, #0x17
```

The complete reply-check paths read these relative offsets:

| Command | Reply size | Bytes read | Unchecked trailer checksum | Check instructions |
|---|---:|---|---|---|
| Enter `0x38` | 15 | 0, 1, 2, 3, 14 | 12, 13 | `0x882e0–0x88314`, `0x88384–0x88390` |
| Send data `0x37` | 7 | 0, 1, 2, 3, 6 | 4, 5 | `0x88694–0x886cc` |
| Program row `0x39` | 7 | 0, 1, 2, 3, 6 | 4, 5 | `0x887e0–0x88818` |
| Verify row `0x3a` | 8 | 0, 1, 2, 3, 4, 7 | 5, 6 | `0x88980–0x889dc` |
| Get row limits `0x32` | 11 | 0, 1, 2, 3, 4, 5, 6, 7, 10 | 8, 9 | `0x88b68–0x88bc8` |

HAL checks transport success, reply status, start/end markers, and expected payload size.
Its lower read wrapper copies bytes after IOKit success without a packet checksum check (`0x24200–0x24218`).
The kext read helper copies register words without a packet checksum check (`0x42d9–0x42f7`).

**Counterexample to a broader claim.** HAL does not ignore every checksum value in replies:

```text
HAL 0x889d0  e8 53 40 39  ldrb w8, [sp, #0x14]
HAL 0x889d4  1f 01 13 6b  cmp w8, w19
HAL 0x889d8  01 02 00 54  b.ne 0x88a18
```

Here reply payload byte four must equal the caller's expected row checksum.
The caller derives that expectation from the file checksum, array, row number, and length (`0x87eb4–0x87ec8`).
HAL also invokes the row-limit helper before program and verify (`0x885f8`, `0x88858`).
Those checks do not compare silicon identity or validate the reply's trailer checksum.

**Inferred safety consequence.** Correct status and markers can conceal corrupted identity, row-limit, or trailer bytes.
A corrupted row-checksum payload can still fail its separate comparison.
**Unknown.** The absent bootloader image prevents a claim that the device itself accepts an incompatible silicon target.

## Remote-I2C timeout propagation

**Refuted as stated. Verified replacement:** the kext logs a timeout, then its miscellaneous dispatcher reports success.
The original code does not produce a structured timeout error that the dispatcher could preserve.

The raw table at `0x406c` maps request one to `0x3da0` and request two to `0x3db3`.
Both branches converge on an unconditional zero return:

```text
Kext 0x3da9  e8 e0 04 00 00  callq 0x428e
Kext 0x3dae  e9 03 02 00 00  jmp 0x3fb6
Kext 0x3dc0  e8 3d 05 00 00  callq 0x4302
Kext 0x3dc5  e9 ec 01 00 00  jmp 0x3fb6
Kext 0x3fb6  45 31 f6        xorl %r14d, %r14d
Kext 0x3fb9  eb 56           jmp 0x4011
Kext 0x4011  44 89 f0        movl %r14d, %eax
```

The read helper calls `_performRemoteI2CTransfer` at `0x42c6`.
It then copies the data window regardless of the transfer outcome (`0x42cb–0x42f7`).
The write helper tail-calls the transfer helper at `0x4383`.

The transfer helper checks register bit 31 at `0x601f–0x6021`.
It polls with `IOSleep(1)` through `0x6028–0x604c`.
On persistent busy, it selects a timeout log message and tail-calls `IOLog`:

```text
Kext 0x604e  85 c0           testl %eax, %eax
Kext 0x6050  78 09           js 0x605b
Kext 0x605b  45 84 f6        testb %r14b, %r14b
Kext 0x6070  31 c0           xorl %eax, %eax
Kext 0x607a  e9 00 00 00 00  jmp _IOLog
```

The final jump has an external relocation. Its zero displacement is not a local branch to the next instruction.
The preceding `xor eax,eax` prepares a variadic call. It is not an IOReturn timeout value.
No path assigns a structured timeout error.

**Verified caller constraints.** Kernel method five has variable input/output structure sizes and no scalar arguments.
Its descriptor at `0x8e88` points to `0x1d72`.
That wrapper requires the correct object class and a non-null provider (`0x1d82–0x1d96`).
The device dispatcher requires its command gate and a request number at most 15 (`0x3d35–0x3d54`).
Both transfer helpers reject lengths above 1024 with a log-only path (`0x428e–0x429f`, `0x4302–0x4313`).
The examined HAL bootloader requests stay below that limit.

HAL translates IOKit return zero to Boolean true at `0x24160–0x24164`.
Its retry wrapper at `0x244b0–0x244ec` cannot retry an error that the kext conceals.

**Inferred safety consequence.** A read timeout can expose old data-window contents as a successful read.
Reply markers and payload checks can reject some stale data, but they cannot restore the lost transport outcome.
This establishes a failure-propagation defect, not unconditional success for the entire firmware update.

## External completion and the device CRC

**Verified device evidence.** PSoC helper `0x18198` computes a byte over data returned by helper `0x124dc`.
That helper reads the FPGA window at `0x60800c00` (`0x1253a–0x1254e`).
The completion loop initializes its CRC state at `0x1823a`, reads blocks at `0x18278`, and updates the CRC at `0x18288`.
The bytewise CRC helper spans `0x218ec–0x21964`. Its eight-bit loop occupies `0x2191a–0x21940`.
The completion helper supplies command `0x61`, an error byte, and the CRC byte:

```text
PSoC 0x182ae  61 23        movs r3, #0x61
PSoC 0x182b0  87 f8 78 30  strb.w r3, [r7, #0x78]
PSoC 0x182c6  87 f8 7b 30  strb.w r3, [r7, #0x7b]
PSoC 0x182ca  97 f8 e3 30  ldrb.w r3, [r7, #0xe3]
PSoC 0x182ce  87 f8 7c 30  strb.w r3, [r7, #0x7c]
PSoC 0x182da  08 f0 1d fb  bl 0x20918
```

**Verified HAL dispatch.** At `0x81710`, HAL reads the command byte from packet offset nine.
Table entry `0xc9c42` contains `90 01`, which resolves command `0x61` to `0x81d80`.
This path requires active state one, then reads only payload byte zero at packet offset `0xd`:

```text
HAL 0x81d80  68 9a 44 b9  ldr w8, [x19, #0x498]
HAL 0x81d84  1f 05 00 71  cmp w8, #1
HAL 0x81d88  61 0f 00 54  b.ne 0x81f74
HAL 0x81d8c  69 a6 46 b9  ldr w9, [x19, #0x6a4]
HAL 0x81d90  88 36 40 39  ldrb w8, [x20, #0xd]
HAL 0x81d94  3f 05 00 71  cmp w9, #1
HAL 0x81d98  61 06 00 54  b.ne 0x81e64
HAL 0x81d9c  48 06 00 35  cbnz w8, 0x81e64
HAL 0x81e64  1f 01 00 71  cmp w8, #0
HAL 0x81e68  48 00 80 52  mov w8, #2
HAL 0x81e6c  08 05 88 1a  cinc w8, w8, ne
HAL 0x81ed8  68 9a 04 b9  str w8, [x19, #0x498]
```

For FPGA type two, error zero directly produces state two. Nonzero error produces state three.
HAL never loads the adjacent CRC byte on this path.
The branch accepts any active type other than resource type one, not only FPGA type two.

**Resource qualification.** For type one and error zero, `0x81da0–0x81db0` requests property `0x40`, selector three.
HAL remains in state one until the version reply.
The raw selector-three table entry at `0xc9c50` resolves to `0x81eac`.
There HAL stores two version bytes, checks active type one and state one, then stores state two (`0x81eac–0x81ed8`).
It neither compares an expected version nor compares a CRC.
The state query returns this stored state at `0x85db0–0x85dc0`.

**Inferred safety consequence.** A completion report with error zero does not establish byte-for-byte image integrity.
The resource version reply supplies an additional protocol dependency, not a host-side integrity test.
**Unknown.** This result does not establish that every physical flash failure yields device error zero.

## CRC type one and caller bounds

**Verified.** The checksum function starts at `0x88c04`.
Type zero sums exactly `length` bytes, negates the sum, and retains 16 bits (`0x88c10–0x88c2c`, `0x88c90–0x88c98`).
Type one instead loads eight distinct bytes per outer iteration:

```text
HAL 0x88c3c  0a 00 80 d2  mov x10, #0
HAL 0x88c40  0b 68 6a 38  ldrb w11, [x0, x10]
HAL 0x88c48  6b 01 00 12  and w11, w11, #1
HAL 0x88c5c  4a 05 00 91  add x10, x10, #1
HAL 0x88c60  5f 21 00 71  cmp w10, #8
HAL 0x88c64  e1 fe ff 54  b.ne 0x88c40
HAL 0x88c68  00 20 00 91  add x0, x0, #8
HAL 0x88c6c  21 04 00 f1  subs x1, x1, #1
HAL 0x88c70  61 fe ff 54  b.ne 0x88c3c
```

For positive length `L`, iteration `j` reads offsets `8*j` through `8*j+7`.
The pointer advances eight bytes, while the outer count decreases by one.
Thus the function reads exactly `8*L` consecutive bytes and uses only each byte's low bit.
For length zero, `0x88c30` branches to a zero return without a read.
The symbol takes an ordinary byte pointer, not a bit-expanded input.
Its callers pass byte counts used to place the packet checksum and end marker.

| Caller | Length passed | Type-one bytes read | Evidence |
|---|---:|---:|---|
| Bootloader entry | 4 | 32 | `0x88250–0x88258` |
| Bootloader exit | 5 | 40 | `0x8832c–0x88334` |
| Row-limit query | 5 | 40 | `0x88b1c–0x88b24` |
| Verify row | 7 | 56 | `0x888f0–0x888f8` |
| Full data chunk | 121 | 968 | `0x88654–0x8865c` |
| Final program chunk for a stock 288-byte row | 61 | 488 | `0x88620–0x8864c`, `0x88780–0x8879c` |

The program helper splits a stock row into 117, 117, and 54 data bytes.
Its full-chunk buffer starts at `sp+0x220` and has a 512-byte zeroed area (`0x88574–0x885b4`).
A 968-byte read exceeds that area and the function's stack frame (`0x8852c–0x88548`).
A short request can exceed its logical packet but remain inside its allocated buffer.

**Verified selection.** Resource offset zero contains ASCII `2E12F0690000`, followed by a newline.
Decoded byte five is zero. HAL stores this byte in `this+0x6a0` at `0x87c00`.
Every examined Ensemble checksum caller loads that field before the checksum call.
The original bundle therefore selects type zero, not the defective type-one loop.

**Reachability qualification.** A header with decoded checksum type one reaches the first 32-byte read before the first transfer.
No HAL header check forbids that type (`0x87bf4–0x87c00`).
The 968-byte case additionally requires accepted bootloader entry, active state one, row parsing, and a successful row-limit response.
A bootloader that rejects the earlier malformed checksums can prevent that later case.
This review does not claim that the stock update reaches a stack over-read.

**Inferred safety consequence.** Type one is not a safe checksum upgrade.
Its result depends on bytes outside the logical request. Large chunks can also read outside the local buffer.

## Safety notes

- Treat transport success, row verification, and complete-image integrity as separate results.
- Do not treat a zero IOKit return as proof that the remote-I2C transfer completed.
- Do not remove the PSoC row-checksum comparison because packet trailer checksums lack validation.
- Do not select checksum type one for a replacement image with this HAL.
- Do not infer silicon compatibility from bootloader-entry success with this HAL.
- Do not infer external-image integrity from error zero or a resource version reply.
- Do not use this report as a flash procedure. The absent PSoC bootloader remains outside the verified image.

## Offline reproduction and checks

The optional verifier reads only installed files. It neither opens a device nor executes vendor code.
Its eight tests check source hashes, transport bytes, reply-read offsets, dispatch tables, completion bytes, the CRC loop, and all firmware records.
The tests pin instruction evidence. They do not emulate hardware or prove every control-flow property in this report.
All eight tests passed. Ruff lint and format checks passed.

```sh
python3 scripts/firmware/verify-update-transport.py -v
ruff check scripts/firmware/verify-update-transport.py
ruff format --check scripts/firmware/verify-update-transport.py
```

For fresh host disassembly, use `llvm-objdump --macho --arch=arm64 --disassemble` on the HAL and updater executables.
Use `--arch=x86_64` for the kext.

No live tests are proposed. Offline evidence settles the stated host behaviors.
Bootloader enforcement and physical failure outcomes remain unknown without additional firmware evidence.
