# Bootloader option-space analysis

The Apogee bootloader is a Cypress Bootloader component, version 1.20. The
scan of 2026-10-14 read this version from the Enter reply, `14 01 01`, which
is 20, 1, 1. The reference source below is version 1.60, which encodes
`{60, 1, 0x01}` (`Bootloader_PVT.h:31`). So each verdict below that depends
on handler details is an inference from a newer version.
`probe-results.md` records the session results.

## Method and sources

The vendor image omits array 0, so the loader's bytes are unavailable.
This analysis instead maps the option space of the public component and
marks each option as determined, constrained, or open, using only prior
verified evidence from this repository.

| Source | Role |
|---|---|
| `Bootloader.h`, `Bootloader.c`, `Bootloader_PVT.h` | Reference component, version 1.60. Commit `55c592ee604eede980094b66533ff8b438f8b0d8` of `dmaone/CommonSense`, path `Bootloader.cydsn/Generated_Source/PSoC5` |
| `Bootloadable.h` | Reference application-side component. Commit `fa1d1eac` of `Infineon/CyScope`, path `ScopeKitProg/Scope_KitProg.cydsn/Generated_Source/PSoC5` |
| AN73854 bootloader application note | Behavior descriptions, already cited in `image-format.md` |

Fetched copies with hashes live in `/tmp/apogee-fw/primary`.
These are a reference project's choices, not Apogee's.
Apogee's own values below follow from evidence in this repository.

## Option verdicts

| Option | Reference value | Apogee determination | Evidence and status |
|---|---|---|---|
| `DUAL_APP_BOOTLOADER` | 0 | **Single app, high confidence.** The CYACD supplies one metadata row, array 3 row 255. A dual build compiles in commands 0x33 and 0x36, which the vendor host never sends. | `image-format.md` coverage table; `updater.md` command inventory. The session does not test it |
| `BOOTLOADER_APP_VERSION` | 0 | Reported by the Enter reply. The app metadata row also stores it as zero. | `Bootloader_PVT.h:22-28`, `image-format.md` metadata table. The session check stage reads it |
| `FAST_APP_VALIDATION` | 0 | **Moot.** The metadata verified byte is zero, so the checksum is computed on every boot either way. | `image-format.md` metadata: verified = 0 |
| `PACKET_CHECKSUM_CRC` | 0 | **Determined: 0, additive.** The CYACD header selects additive, and the HAL checksum routine sums bytes. | CYACD header byte 10; `verify-update-transport.md` CRC section |
| `WAIT_FOR_COMMAND` | 0 | **Not unconditional.** The unit boots its application at every power-on, so the loader does not wait forever by default. | Front-panel operation without a host |
| `BOOTLOADER_APP_VALIDATION` | 1 | **Enabled and passing.** With the verified byte zero and a booting application, the whole-image checksum passes every boot. | `image-format.md` checksum section |
| `CMD_GET_FLASH_SIZE_AVAIL` | 1 | **Enabled.** The host sends 0x32 in every update. | `updater.md` phase table |
| `CMD_SEND_DATA_AVAIL` | 1 | **Enabled.** The host sends 0x37 before each program. | Same |
| `CMD_GET_ROW_CHKSUM_AVAIL` | 0 in reference | **Enabled in Apogee's build.** The host's verify step sends 0x3A and the reply carries a computed checksum byte. | `verify-update-transport.md` reply table. This is a deviation from the reference's default |
| `CMD_ERASE_ROW_AVAIL`, `CMD_SYNC_BOOTLOADER_AVAIL`, `CMD_GET_METADATA`, `CMD_VERIFY_FLS_ROW_AVAIL`, `CMD_VERIFY_APP_CHKSUM_AVAIL` | 0 | Unknown. The host never sends them, but absence of use is not proof of absence. | Open. The dext refuses them, so the session cannot test them |
| `SECURITY_KEY_AVAIL` | 0 | **Constrained: absent.** The observed host Enter request carries no key bytes. The zero-data Enter of the session check stage confirms it. | `updater.md`, `verify-update-transport.md` |
| `AUTO_SWITCHING_AVAIL` | 1 | Moot for a single-app classic loader. | Same basis as dual-app |
| `GOLDEN_IMAGE_AVAIL` | 0 | **Constrained: not applicable.** A golden image belongs to launcher builds. No golden slot appears anywhere in the CYACD. | `Bootloader.c` launcher sections |
| Loader size | set by linker | **Determined: 64 KB reserved, 70 rows used.** The metadata records bootloader last row 255. The scan found nonzero row checksums in rows 0 to 69 of array 0 only | `image-format.md` metadata table, `probe-results.md` |
| ECC | set by the `ECCEN` latch | **Determined: off.** All 355 image rows match the 288-byte row sums. Only 206 match the 256-byte sums | `probe-results.md` |
| Loader row protection | `row < firstRow` refusal in 1.60 | **Open.** Report size answers rows 0 to 1023 for every array, so the reply does not show a protected loader region. Do not write array 0 until the 1.20 program-row guard is known | `probe-results.md` |

## Recovery consequences

**Verified from the reference algorithm, `Bootloader.c:1075-1097`:**
if the application is invalid, or the run type requests it, the loader
calls `HostLink(WAIT_FOR_COMMAND_FOREVER)`. The loader then answers
commands after every reset until Exit.

**Verified from the reference algorithm, `Bootloader.c:1092`:** the loader
clears the run type before it waits. The application sets that run type
in `RESET_SR0` before its software reset (`psoc-update.md`).

**Inferred:** after a power cycle, the loader starts the application if
the application checksum passes. A session that stops in the loader
therefore ends at the next power cycle. Apogee's loader bytes are absent,
so this holds for the reference loader only.

**Inferred:** a partial or interrupted application update leaves the
whole-image checksum wrong, because row writes are single-row operations
and the metadata checksum covers all application rows. The next boot
then lands in the loader instead of a broken application. This is an
automatic recovery property that the vendor path relies on.

**Inferred:** the cost is that a failed update still erases the old
application rows before the replacement completes. The loader protects
itself, not the application.

## Command reference

The reference dispatcher sets the reply status to `ERR_DATA` (0x04)
before it selects a handler (`Bootloader.c:1771`). A known command with
a wrong payload length therefore returns 0x04. An unknown command goes to
`Bootloader_callback` if the build registers one (`Bootloader.c:2692`).
Only without a callback does it return `ERR_CMD` (0x05). Apogee code in
that callback can act on any unknown command.

| Byte | Command | Reference behavior | Session use |
|---|---|---|---|
| 0x38 | Enter | Reply: status, 32-bit silicon ID, revision, 3-byte loader version | Sent, no data |
| 0x32 | Report size | Flash arrays 0 to 3 only. The last row is inclusive (`Bootloader.c:2007`) | Sent for arrays 0 to 3 |
| 0x3A | Get row checksum | Reads one row of a flash array or of EEPROM array 0x40. No write | Sent for every flash and EEPROM row |
| 0x3B | Exit | No reply. Resets into the application if it is valid (`Bootloader.c:2650-2680`) | Sent with one zero byte, as the vendor sends it |
| 0x34 | Erase row | A well-formed request erases a row | **Refused by the dext** |
| 0x36 | Set active application | A well-formed request rewrites the metadata row in a dual-app build (`Bootloader.c:2396`) | **Refused by the dext** |
| 0x37, 0x39 | Data, program row | Write flash | **Refused by the dext** |
| 0x35 | Sync | Sends no reply (`Bootloader.c:2376`) | Refused by the dext |
| 0x31, 0x33, 0x3C, 0x45 | Checksum, app status, metadata, verify row | Reads in the reference. Unknown in Apogee's build | Refused by the dext |

Error codes from `Bootloader_PVT.h:51-64`: key 0x01, verify 0x02, length
0x03, data 0x04, command 0x05, device 0x06, version 0x07, checksum 0x08,
array 0x09, row 0x0A, protect 0x0B, app 0x0C, active 0x0D, callback 0x0E.

## Read-only bootloader session plan

The session reads the loader identity, the flash layout, and the checksum
of every flash and EEPROM row. It writes no flash. It changes one device
state: the application writes a four-byte EEPROM restart marker before
it resets into the loader.

### Glossary

- **Session**: the right to send command 0x60 and to use the remote-I2C
  engine. One user client of the dext holds it at a time.
- **Status**: BAR0 `INFO` bits 7:6. The value 1 means the PSoC
  application runs. The value 2 means its bootloader runs.
- **Engine**: the FPGA remote-I2C engine, BAR0 `0x18` and window `0x3C00`.
- **Power cycle**: removal of mains power. The front-panel power button is
  not a power cycle. The application handles that button and enters its
  software-off state with the PSoC still on (`psoc-scheduler.md`). In the
  bootloader, the application does not run, so the button has no known
  effect.

### Safety rules that the dext enforces

The session tool cannot pass these rules. Another user client cannot
pass them either.

| Rule | Code | Reason |
|---|---|---|
| One client holds the session. The dext refuses the session while audio runs, and refuses `StartIO` while the session is open | `EnsembleDevice::OpenSession`, `StartIO` | The PSoC reset stops audio. Two clients can interleave engine writes |
| Command 0x60 passes only in a session, as type 1 with p1 0 and value 0 | `isBootloaderEntry` in `Protocol.h` | Other 0x60 values start an external flash update |
| A transfer passes only while the status is 2 | `EnsembleDevice::TransferI2c` | The application can own the same bus. The vendor opens the engine only at status 2 (`verify-recovery.md`) |
| A write passes only as Enter with no data, report size for arrays 0 to 3, row checksum for arrays 0 to 3 and 0x40, or Exit with one zero byte. Start, stop, length, and checksum must be correct | `validBootloaderPacket` in `I2c.h` | These are the read commands that the vendor updater sends, in its shape |
| A transfer carries at most 255 bytes | `kI2cMaxBytes` | The count field is bits 15:8. A larger count changes the 0x6C field |
| The engine turns on at the first transfer, waits 3 s, and turns off when the session closes | `EnsembleDevice::TransferI2c`, `CloseSession` | The vendor updater enables the engine once and sleeps 3 s before Enter (`updater.md`) |

### Preconditions

1. Record the owner approval.
2. Connect power to the unit before Thunderbolt. Apogee documents this
   order for recovery from a half-loaded boot.
3. Run `make install` with this commit, so that the dext enforces the
   rules above.
4. Quit every audio application. The dext refuses the session while audio
   runs.
5. Run `driver/test.sh`, `swift test` in `control/`, and
   `python3 scripts/firmware/bootloader-rows-test.py`. All must pass.
6. Run `make bootloader`. The tool is
   `control/.build/release/ensemble-bootloader`.
7. Run `ensemble-bootloader status`. It must print 1.
8. Keep the Apogee Firmware Updater installed. Read the recovery table
   below before the first stage.

### Check stage

Run `ensemble-bootloader check`. This stage proves the transport and the
exit path before the long scan. The tool does these steps:

1. It reads the status. If the status is not 1, it stops.
2. It opens the session.
3. It sends command 0x60 mode 0. The application writes `CD AB 01 00`
   at EEPROM offset 0x7F0, writes zero to FPGA register 0x2D, and resets
   into the loader. Audio stops.
4. It polls the status every 10 ms, for a maximum of 10 s, until the
   status is 2.
5. The first transfer turns on the engine. The dext waits 3 s.
6. It sends Enter with no data. It waits 28 ms, then reads 15 bytes. If
   the transport fails, it tries again, a maximum of 20 times. If the
   loader returns an error status, it does not try again.
7. It sends Exit with one zero byte, and reads no reply.
8. It polls the status every 10 ms, for a maximum of 10 s, until the
   status is 1.
9. It closes the session. The dext turns off the engine.

If an error occurs after step 4, the tool still does steps 7 and 8.

Expected output: eight bytes. The first four are `69 f0 12 2e`, the
silicon ID 0x2E12F069 as a little-endian word. Then come the revision and
the 3-byte loader version.

After the stage, run `make status`, read a setting through
ensemble-control, and play audio. Do not continue if any of these fails.

### Scan stage

Run `ensemble-bootloader scan --json scan.json` only after a successful
check stage. The stage takes about 2 minutes. Between Enter and Exit, the
tool makes two passes. Each pass sends report size for arrays 0 to 3,
then row checksum for 1024 flash rows and 128 EEPROM rows. The second
pass runs in the opposite order.

The loader protocol has no sequence number. A read before the loader
replaces its reply returns the previous reply, with a valid checksum. In
opposite orders, such a stale reply gives a different value in each pass.
If the passes differ, the tool stops with an error, sends Exit, and
writes no file.

Then run `python3 scripts/firmware/bootloader-rows.py scan.json`.

Success criteria:

- The two passes agree.
- The silicon ID is 0x2E12F069.
- Report size answers for arrays 0 to 3. The comparator records the
  reply. On this unit the v1.20 loader answers rows 0 to 1023 for every
  array.
- All 355 rows of the vendor CYACD match. A match of the 288-byte row
  sums means that ECC is off. A match of the 256-byte sums means that
  ECC is on.
- The status is 1 after the stage, and audio plays.

The output also records `loader_fingerprint_sha256`, a hash of the
256 row checksums of array 0. It identifies the loader build across
units. It is not the loader bytes.

### Recovery

| Symptom | Next action |
|---|---|
| The tool reports `PSoC status stayed 0, not 2` or another value after 0x60 | Wait 10 s. Run `ensemble-bootloader status`. If it prints 2, run `ensemble-bootloader exit`. If it prints 1, the application runs again. For other values, power-cycle the unit |
| The tool reports an error and the status is 2 | Run `ensemble-bootloader exit` |
| The tool or the Mac stops during a stage | Run `ensemble-bootloader status`. If it prints 2, run `ensemble-bootloader exit` |
| `exit` fails, or the dext refuses the transfer | Disconnect Thunderbolt. Disconnect the power cord for 10 s. Connect it, turn the unit on, and wait for the front panel. Then connect Thunderbolt |
| The status is 2 after a power cycle | The application checksum fails, or Apogee's loader differs from the reference. Run `make uninstall`, then the Apogee Firmware Updater. When the HAL finds status 2, it sends Exit first, then it can program the PSoC (`updater.md`) |

### Commands that the session does not send

- 0x37, 0x39, 0x34, 0x36: they write flash or metadata.
- 0x35: it sends no reply, so the next read returns a stale reply.
- 0x31, 0x33, 0x3C, 0x45: their handlers are unknown in Apogee's build,
  and an unknown command can reach Apogee code. A test of these commands
  waits for the loader bytes.
- 0x32 for array 0x40: the reference loader rejects it.

### Residual risks

- Apogee's loader can differ from the reference. The vendor updater sends
  Enter, report size, row checksum, and Exit on every PSoC update. It
  sends row checksum for application rows only. Row checksum for array 0
  and for EEPROM rows is a read in the reference, but it is new to this
  loader.
- Each session writes the EEPROM marker row. The application clears a
  marker byte at its next start, which is a second row write.
- The 28 ms reply delay comes from the vendor updater. The two-pass
  comparison detects a delay that is too short.
- If the loader changes the status during a session, the dext refuses
  every transfer, Exit included. A power cycle then ends the session.
- The first scan run on 2026-10-14 stopped with a broken reply, and a
  second run passed. That build did not record the bytes, so the cause is
  unknown. The tool now names the command and the bytes. If it recurs,
  compare the bytes with the previous reply and with all `ff`.

## Limits

- The loader's exact version and any Apogee custom commands stay unknown
  until the session runs.
- The transport wiring, which pins the FPGA I2C bridge drives, and the
  bus owner outside a session remain hardware questions.
- A checksum fingerprint is not the loader's bytes. Reconstructing them
  still needs physical debug access.
