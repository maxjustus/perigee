# Plan: guards for the user client send channel

Keep hostile records away from the PSoC parser. The firmware has six
confirmed defects. Three of them accept hostile input through the send
channel.

## Terms

- **Dext**: the DriverKit extension in `driver/`. It replaces the vendor kext.
- **PSoC**: the device microcontroller. It parses mailbox messages.
- **Mailbox**: the FPGA register ring that carries messages in both directions.
- **User client**: the DriverKit object that a userspace process opens. Its
  `Send` selector forwards a message to the mailbox.
- **Slot state**: the per-slot register that carries the message length. The
  firmware masks it with `0x1F`.
- **Bootloader**: the PSoC boot program that receives firmware rows.

## Why

Offline verification confirmed the six defects. The evidence lives in
[verify-mailbox.md](firmware/verify-mailbox.md),
[verify-memory-safety.md](firmware/verify-memory-safety.md),
[verify-update-transport.md](firmware/verify-update-transport.md), and
[verify-recovery.md](firmware/verify-recovery.md).

Exposure of the current dext:

| Firmware defect | Exposure today |
|---|---|
| A slot state length of 31 overwrites a timer callback | None. `Mailbox.h` caps the length at 30 words. The overwrite starts at 31. The verification doc calls for at most 29, because the 120-byte firmware buffer bound is inferred. |
| Command `0x62` trusts the count byte over the payload length | Open. `EnsembleUserClient.cpp` copies arbitrary user words with no command check. |
| The resource loader copies its index before the CRC check | Open. Resource data travels in `0x62` packets on the same channel. |
| EEPROM replay trusts descriptor widths | Unresolved. The dext sends value writes only. No mailbox command that writes descriptor bytes was confirmed. |
| The report serializer under-reports its word count | None. `Protocol.h` clamps the claimed length to the bytes the slot holds. |
| Bridge timeouts never reach the update status | None. The dext replaces the vendor kext and has no update transport. |

Two more parser defects read the same channel:

- For type-2 records with length 1 to 3, the parser advances three words. The
  record body occupies two words. A record that follows is misread.
- For record types 3 and 4, the parser leaves the record pointer unchanged. A
  record that follows is skipped.

## Changes

### Send-channel validator

Add `validMessage` to `Protocol.h`. Call it from
`EnsembleUserClient::ExternalMethod` before `Send`. Write the tests in
`protocol_test.cpp` first. The dext builds its own messages from constants,
so only user client input passes the validator.

The validator walks the record bytes in one pass:

1. Words 0 and 1 are the header. Record bytes start at offset 8.
2. Accept record types 1, 2, and 4 only.
3. Reject a record whose command byte is `0x60`, `0x61`, `0x62`, `0x63`,
   `0xD6`, or `0xD7`. These carry bootloader entry, firmware selectors,
   update data, the restart-state store, and the DSP core erase and halt.
4. Require exactly one record. The record must end inside the final word of
   the message. The pad bytes after the record must be zero.

Current senders comply. The dext sends get-all and type-1 sets. The control
service sends type-1 sets, type-2 blocks with count 1 or 2, and get-all. Each
message carries one record.

Commit: `fix(driver): validate user client messages before the mailbox`

### Send-length cap of 29 words

Add `kSendSlotWords = 29` to `Protocol.h`. Use it in the `Mailbox.h` send guard
and in the user client length check. Keep `kSlotWords = 30` for the receive
clamp. Write the tests in `mailbox_test.cpp` first.

Reason: the emulation proves that a length of 30 stays inside the firmware
buffer. The buffer bound is inferred from data layout, not from a recovered
declaration. No sender uses more than 3 words today. Take the margin.

Commit: `fix(driver): cap mailbox send length at 29 words`

### EEPROM reachability research

Decide whether a mailbox command writes EEPROM descriptor bytes. Use
`scripts/firmware/psoc-protocol-map.py` and the name tables in
`docs/firmware/names/`. Record the answer in `verify-memory-safety.md`.

The answer decides whether the deny list needs more commands. No dext change
in this step unless the answer demands one.

Commit: `docs(firmware): record the EEPROM descriptor write path`

## Decisions

- **Deny list, not allow list.** The control service sends 38 distinct
  command bytes today. An allow list needs a sync between the Swift parameter
  table and the dext. The deny list closes the update and DSP paths with no
  coupling.
- **One record per message.** The type-2 parser skip makes multi-record
  messages unsafe. All current senders send one record. A future batched
  restore must revise this rule with hardware tests.
- **Cap of 29, not 30.** See the send-length step. The cost is zero because
  no sender uses more than 3 words.

## Acceptance

- A message that contains a denied command returns `kIOReturnBadArgument`
  from the user client.
- A message with two records returns `kIOReturnBadArgument`.
- A message longer than 116 bytes returns `kIOReturnBadArgument`.
- `driver/test.sh` passes.
- The control service still sets sample rate, clock source, and monitor
  volume. Verify on hardware after `make install`.

## Out of scope

- A firmware updater. An updater must use a separate gated path, plus the
  offline validators from the firmware docs: row checksums, resource decode,
  and image CRC.
- Firmware fixes. The device runs the vendor application.
- The `Bar0` read status blindness. `Bar0.h` ignores the `MemoryRead32`
  status and returns zero. A wedged FPGA yields zero or stale registers. That
  defect class touches the register layer, not the send channel. It needs its
  own plan.
