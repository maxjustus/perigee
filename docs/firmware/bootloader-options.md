# Bootloader option-space analysis

The Apogee bootloader is a Cypress Bootloader component build of the 1.60
generation. Our verified evidence constrains most of its design-time options.
The loader itself can be fingerprinted, but not read, through one
read-only session.

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
| `DUAL_APP_BOOTLOADER` | 0 | **Single app, high confidence.** The CYACD supplies one metadata row, array 3 row 255. A dual build compiles in commands 0x33 and 0x36, which the vendor host never sends. | `image-format.md` coverage table; `updater.md` command inventory. Confirm in R7 |
| `BOOTLOADER_APP_VERSION` | 0 | Reported by the Enter reply. The app metadata row also stores it as zero. | `Bootloader_PVT.h:22-28`, `image-format.md` metadata table. Read in R7 |
| `FAST_APP_VALIDATION` | 0 | **Moot.** The metadata verified byte is zero, so the checksum is computed on every boot either way. | `image-format.md` metadata: verified = 0 |
| `PACKET_CHECKSUM_CRC` | 0 | **Determined: 0, additive.** The CYACD header selects additive, and the HAL checksum routine sums bytes. | CYACD header byte 10; `verify-update-transport.md` CRC section |
| `WAIT_FOR_COMMAND` | 0 | **Not unconditional.** The unit boots its application at every power-on, so the loader does not wait forever by default. | Front-panel operation without a host. R7 can measure the boot delay |
| `BOOTLOADER_APP_VALIDATION` | 1 | **Enabled and passing.** With the verified byte zero and a booting application, the whole-image checksum passes every boot. | `image-format.md` checksum section |
| `CMD_GET_FLASH_SIZE_AVAIL` | 1 | **Enabled.** The host sends 0x32 in every update. | `updater.md` phase table |
| `CMD_SEND_DATA_AVAIL` | 1 | **Enabled.** The host sends 0x37 before each program. | Same |
| `CMD_GET_ROW_CHKSUM_AVAIL` | 0 in reference | **Enabled in Apogee's build.** The host's verify step sends 0x3A and the reply carries a computed checksum byte. | `verify-update-transport.md` reply table. This is a deviation from the reference's default |
| `CMD_ERASE_ROW_AVAIL`, `CMD_SYNC_BOOTLOADER_AVAIL`, `CMD_GET_METADATA`, `CMD_VERIFY_FLS_ROW_AVAIL`, `CMD_VERIFY_APP_CHKSUM_AVAIL` | 0 | Unknown. The host never sends them, but absence of use is not proof of absence. | R7 command probe settles each one |
| `SECURITY_KEY_AVAIL` | 0 | **Constrained: absent.** The observed host Enter request carries no key bytes. A zero-data Enter in R7 confirms it. | `updater.md`, `verify-update-transport.md` |
| `AUTO_SWITCHING_AVAIL` | 1 | Moot for a single-app classic loader. | Same basis as dual-app |
| `GOLDEN_IMAGE_AVAIL` | 0 | **Constrained: not applicable.** A golden image belongs to launcher builds. No golden slot appears anywhere in the CYACD. | `Bootloader.c` launcher sections |
| Loader size | set by linker | **Determined: 64 KB.** The metadata records bootloader last row 255. | `image-format.md` metadata table |

## Recovery consequences

**Verified from the reference algorithm, `Bootloader.c:1075-1097`:**
if the application is invalid, or the run type requests it, the loader
calls `HostLink(WAIT_FOR_COMMAND_FOREVER)`. The loader then answers
commands after every reset until Exit.

**Inferred:** a partial or interrupted application update leaves the
whole-image checksum wrong, because row writes are single-row operations
and the metadata checksum covers all application rows. The next boot
then lands in the loader instead of a broken application. This is an
automatic recovery property that the vendor path relies on.

**Inferred:** the cost is that a failed update still erases the old
application rows before the replacement completes. The loader protects
itself, not the application.

## Command reference

| Byte | Command | Reference status | R7 use |
|---|---|---|---|
| 0x38 | Enter | Standard | Open the session. Reply: status, 32-bit silicon ID, revision, 3-byte loader version |
| 0x32 | Report size | Standard, enabled | Read array layout and the loader's last row |
| 0x3A | Get row checksum | Enabled in Apogee's build | Read one computed checksum byte per row, any array, no write |
| 0x3B | Exit | Standard | Reset into the application |
| 0x31, 0x33, 0x34, 0x35, 0x36, 0x3C, 0x45 | Checksum, app status, erase, sync, active app, metadata, verify row | Unknown in Apogee's build | Probe each. An unknown command returns `ERR_CMD` (0x05) without side effects |
| 0x37, 0x39 | Data, program row | Standard, enabled | **Not sent in R7.** They write flash |

Error codes from `Bootloader_PVT.h:51-64`: key 0x01, verify 0x02, length
0x03, data 0x04, command 0x05, device 0x06, version 0x07, checksum 0x08,
array 0x09, row 0x0A, protect 0x0B, app 0x0C, active 0x0D, callback 0x0E.

## R7 session plan, offline draft

Preconditions: owner approval recorded, unit on the open driver, no audio
clients. Every command below is read-only. No 0x37 or 0x39 is ever sent.

1. Send application command 0x60 mode 0. This writes the four-byte EEPROM
   restart marker at 0x7F0 and resets the PSoC. Audio stops. The vendor
   updater performs this on every PSoC update.
2. Wait for bootloader status 2 through the kext INFO register, then open
   the remote-I2C channel.
3. Send Enter 0x38 with zero data. Expect success plus eight bytes. If the
   reply is an error instead, the security key is active. Abort with Exit
   and stop.
4. Send 0x32 for arrays 0 to 3 and 0x40. Array 0 must answer with start
   row 256, which reconfirms the 64 KB loader size live.
5. Send 0x3A for every row of array 0. That is 256 checksum bytes, the
   loader's fingerprint. Repeat for arrays 1 to 3 and EEPROM array 0x40.
6. Compare the array 1 to 3 replies against row sums computed offline
   from the CYACD. Agreement validates both the device state and our
   protocol understanding before any future write.
7. Probe 0x31, 0x33,0x34,0x35,0x36,0x3C,0x45 with well-formed requests.
   Record enablement per command.
8. Send Exit 0x3B. The application restarts, clears the marker, and
   resumes normal operation.

Success criteria: silicon ID matches `0x2E12F069`, array-0 start row is
256, vendor row sums match for arrays 1 to 3, Exit restores the unit.

## Limits

- The loader's exact version and any Apogee custom commands stay unknown
  until the session runs.
- The transport wiring, which pins the FPGA I2C bridge drives, and the
  bus owner outside a session remain hardware questions.
- A checksum fingerprint is not the loader's bytes. Reconstructing them
  still needs physical debug access.
