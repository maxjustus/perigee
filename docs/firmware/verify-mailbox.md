# Independent verification of the mailbox copy and timer storage

The original instructions confirm that a slot state length of 31 overwrites the first timer callback.
The scheduler then loads that overwritten word as its branch operand.

## Scope and method

This review used the vendor application bytes only.
The input is `/tmp/apogee-fw/flash.bin`, 196,608 bytes, SHA-256
`a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8`.
A Unicorn emulator executed the original Thumb instructions.
Every run required the expected return address or an explicit stop address.
The verifier refuses optimized Python, because optimization removes its assertions.

Reproduce:

```sh
uv run --with unicorn==2.1.4 python scripts/firmware/verify-mailbox.py
uv run --with unicorn==2.1.4 python -O scripts/firmware/verify-mailbox.py
```

The second command must print the optimization refusal and exit nonzero.

## Confirmed claims

### The copy loop writes word 30 into the timer table

**Confirmed.** `0x1204C–0x12052` derives the word count as `state & 0x1F`.
`0x12040–0x12046` computes the source as FPGA mailbox `0x60800800 + 120*slot`.
The loop at `0x120B8` stores four-byte words to the destination.

**Confirmed.** The receive destination is `0x1FFFA030`.
The timer slots begin at `0x1FFFA0A8`.
Word index 30 therefore stores to `0x1FFFA030 + 4*30 = 0x1FFFA0A8`.
The 120-byte buffer size follows from the adjacent data layout, not from a recovered declaration.

**Confirmed by emulation.** With slot state 31, the 31st store placed the marker word
exactly at `0x1FFFA0A8`, the first timer callback pointer.
States 32 through 63 and `0x8000001F` also mask to 31 words through `and r3, r3, #0x1F`.

### The scheduler consumes the overwritten word

**Confirmed.** The emulation stopped at `0x2033A`, before `blx r3`.
Register `r3` held the overwritten marker word, and register `r0` held the argument slot value.
So the scheduler loads the overwritten word as its call target operand.
The test never executed the corrupt branch.

### The receive gate does not restrict the copy

**Confirmed.** `0x15F34` loads the protocol state, subtracts three, and compares.
Both branches load the constant one: `movs r3, #1` at `0x15F42` and at `0x15F48`.
The function returns one for every protocol state.
Seven emulated state probes, `0` to `5` and `0xFFFFFFFF`, all returned one.

### Rejection cases behave as documented

**Confirmed.** An empty ring, a null destination, and a null count pointer copy nothing.
The slot state and indices stay unchanged in those cases.

## Test coverage

| Group | Cases | Result |
|---|---:|---|
| Direct copy: slots 0..7, states 0..63, five high-bit states | 552 | Pass |
| Rejection: empty ring, null destination, null count | 3 | Pass |
| Interrupt-to-outer path: six states per slot | 48 | Pass |
| Outer gates: idle, unrelated event, host states, pending drain | 5 | Pass |
| Protocol-state probes of `0x15F34` | 7 | Pass |
| Callback consumption at the branch operand | 1 | Pass |

Every case verified the store sequence, the source reads, the consumed slot,
the ring indices, and the destination bytes.

## Reachability limits

**Inferred.** The slot state is host-written data, not firmware output.
The vendor kext writes at most 29 words per slot, so the vendor host path cannot set 31.
A replacement host or replacement firmware that writes a state length of 31 triggers the overwrite.

**Unknown.** No test executed the overwritten callback on hardware.
The emulation proves the store, the scheduler load, and the operand use.
It does not prove a runtime fault sequence on the unit.

## Safety notes

- A replacement host driver must never write a slot state length of 31.
- A replacement firmware must bound the copy to the receive buffer.
- Do not treat the `0x15F34` gate as a protocol-state guard. It returns one unconditionally.
