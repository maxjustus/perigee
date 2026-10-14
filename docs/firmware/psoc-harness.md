# PSoC application harness

A Unicorn harness boots the vendor application image offline and answers
real host commands through an emulated FPGA. It is the verification
instrument for a modified image before any flash.

## What runs on real instructions

Everything except the registered substitutes below. In particular:

- The complete dispatcher: a type-3 Get written into a transmit slot is
  consumed by the real receive path, dispatched by the real command table,
  and answered by the real report serializer.
- The version pipeline: the refresh routine stores live values into the
  state pool, including a full-resource CRC-8 computed by real vendor
  instructions over the vendor resource image read through the emulated
  flash bridge.
- The settings and scheduler initialization, the mailbox ring protocol,
  TX/RX index and state transitions, and the host handshake to
  protocol-ready state 2.

The harness reproduces the live device's reports exactly:
Get 0x40 selector 0 answers `01 05 03` and selector 3 answers `00 06 1b`.
The latter is derived, not hard-coded: the CRC is computed over the vendor
`EnsembleResourceData.bin` placed in the emulated flash at `0x380000`.

## Substitutes

Each substitute hooks a function entry, performs the replacement, and jumps
to the return address. Hits are counted.

| Address | Replaced function | Reason |
|---|---|---|
| 0x23064 | EEPROM row write | Backing array instead of the real EEPROM array |
| 0x232BC | Timer counter read | Emulated tick source |
| 0x23AD4, 0x23B18 | CyDelay, CyDelayUs | No real time passes |
| 0x12610 | FPGA word write | EMIF byte writes applied to the emulated FPGA window |
| 0x108BC, 0x22244, 0x22B94 | Preamp register, preamp SPI, display SPI | Real silicon absent |
| 0x11050, 0x110C0, 0x110F0 | I2C wrappers | Real bus absent |
| 0x2278C, 0x22898, 0x229A8, 0x229E4 | I2C master primitives | Real bus absent |

The flash bridge inside the FPGA window is emulated at the data level:
commands 0x02 erase, 0x10 program, and 0x12 read operate on a backing
array that holds the resource image at `0x380000`.

## Limits

- Cold boot from the reset handler runs 2 million instructions and then
  stalls at `0x22b6c`, in early peripheral initialization. Warm start is
  the supported entry. A future pass must identify the blocking poll to
  finish cold boot.
- EEPROM writes, I2C, SPI, and preamp substitutes are registered but not
  exercised by the current test paths. They fire on settings saves, audio
  control changes, and display activity.
- The emulated FPGA answers from a model, not the vendor bitstream. DSP
  core behavior beyond the version registers is absent.
- Nothing here proves hardware safety. It proves dispatch, state, and
  report behavior on real vendor instructions.

## Use

```sh
uv run --with unicorn==2.1.4 python scripts/firmware/psoc-harness-test.py
```

A modified image is verified by swapping its bytes for the flash image,
rerunning the suite, and comparing every report and state transition
against the vendor baseline. The builder `cyacd-build.py` produces the
image; the inspector gates it first.

Input identity is pinned: `flash.bin` SHA-256
`a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8`.
The harness refuses optimized Python, because optimization removes its
assertions.
