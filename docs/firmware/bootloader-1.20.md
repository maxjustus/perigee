# Bootloader 1.20 guards

The unit runs Cypress Bootloader component 1.20. In a single-application
build, that version does not refuse a program or erase request for a
loader row. One such request can overwrite the only copy of the loader.
The host must enforce that boundary.

## Glossary

- **Loader**: the PSoC bootloader in flash array 0. It is absent from the
  vendor CYACD.
- **Single-application build**: a loader built with
  `Bootloader_DUAL_APP_BOOTLOADER` set to 0. The vendor CYACD has one
  metadata row, so the Apogee loader is this build
  (`bootloader-options.md`).
- **Metadata row**: array 3, row 255. It holds the application checksum,
  length, and entry point.

## Explanation

### Why this source applies

The Enter reply of the unit carries the version bytes `14 01 01`
(`probe-results.md`, "Bootloader check stage"). The 1.20 source below
defines `Bootloader_VERSION` as `{(uint8)20, (uint8)1, (uint8)0x01u}`. The
1.60 source defines `{60, 1, 0x01}`.

The report-size reply agrees. The unit answers first row 0 and last row
1023 for every array. The 1.20 handler sets the first row to 0 when the
part has more than one flash array, and the last row to
`CY_FLASH_NUMBER_ROWS - 1`. The CY8C5268 has 1024 rows. The 1.60 handler
answers per array, with the last row 255.

The source is generator output from a third-party project, not Apogee's
build. Its `Generated_Source` copy is byte-identical to its `codegentemp`
copy, so nobody edited it by hand. Apogee's options can differ. The
guards below do not depend on an option that the unit's evidence leaves
open.

### What the loader protects

| Region | 1.20 single-application behavior | Consequence |
|---|---|---|
| Loader rows, array 0 | No check. Program and erase write any row | A write to array 0 can destroy the loader. If the build checks its own checksum (`Bootloader_BOOTLOADER_APP_VALIDATION`), start-up then halts the CPU (`CyHalt`) |
| Metadata row | The first program or erase of a session writes zeros to it | The application is invalid from the first write until the host writes the new metadata row. An interrupted update then stops in the loader |
| Row number of program and erase | No range check before `CyWriteRowFull` | The flash routine is the only bound. Its checks are not part of this source |
| Row number of row checksum | No range check | A flash row above 255 reads past its array. An EEPROM row above 127 reads peripheral registers |
| Unknown command | Returns `ERR_CMD`. No callback exists in 1.20 | An unknown command has no side effect in the generated code |
| Enter | Accepts only zero data bytes. No security key exists in 1.20 | The check stage result agrees |

Component 1.30 adds the missing loader guard: "Refuse to write to the row
within range of the bootloader application", with `row < firstRow`
returning `ERR_ROW`. So the gap is specific to the version on the unit.

### Recovery

The 1.20 start-up clears the run type before it waits for commands. If the
application is invalid, the loader waits forever. A power cycle therefore
boots a valid application, and returns to the loader when the application
is invalid. Both depend on an intact loader.

## Reference

### Source

| Item | Value |
|---|---|
| Repository | [honet/C86BOX-BOOTFW](https://github.com/honet/C86BOX-BOOTFW) |
| Commit | `2d7d94c30d206837d0d231c1bc8a953ff1c21434` |
| Path | `c86usb_bootloader.cydsn/Generated_Source/PSoC5/` |
| `Bootloader.c` SHA-256 | `49985582e95d7a01db180f43381523b05a915a6bdb19e83095971d10249c9d05` |
| `Bootloader_PVT.h` SHA-256 | `e00d3a783e7c9c240d793844f01129e088d90ae6bf1c89ec7621b54bd18f485f` |
| `Bootloader.h` SHA-256 | `348dda1872b83362daa6d0c6cc503f4c562ab3dbb292b81dc48f49d7fc1263d1` |
| Local copy | `/tmp/apogee-fw/bootloader-1.20` |

### Line references

Base URL:
`https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/`

| Behavior | Lines |
|---|---|
| Version bytes | [`Bootloader_PVT.h#L30-L34`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader_PVT.h#L30-L34) |
| Loader checksum, `CyHalt` on mismatch | [`Bootloader.c#L320-L342`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c#L320-L342) |
| Run type cleared before the wait | [`Bootloader.c#L356-L361`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c#L356-L361) |
| Report size: first row 0, last row 1023 | [`Bootloader.c#L759-L780`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c#L759-L780) |
| Program and erase, metadata zeroed, no loader check | [`Bootloader.c#L818-L1015`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c#L818-L1015) |
| Enter with zero data only | [`Bootloader.c#L1110-L1140`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c#L1110-L1140) |
| Row checksum, no row bound | [`Bootloader.c#L1148-L1224`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c#L1148-L1224) |
| Exit without a reply | [`Bootloader.c#L1230-L1240`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c#L1230-L1240) |
| Unknown command: `ERR_CMD` | [`Bootloader.c#L1246-L1248`](https://github.com/honet/C86BOX-BOOTFW/blob/2d7d94c30d206837d0d231c1bc8a953ff1c21434/c86usb_bootloader.cydsn/Generated_Source/PSoC5/Bootloader.c#L1246-L1248) |
| 1.30 loader guard, for comparison | [`glocklueng/032` `Bootloader.c#L1126-L1141`](https://github.com/glocklueng/032/blob/69bb94e002867f14048c0c9907ce5731bfab5f15/LayerOne_2016/firmware/BadgeFirmware/UART_Bootloader.cydsn/Generated_Source/PSoC4/Bootloader.c#L1126-L1141) |

## Rules for a flash write path

These rules hold for any future write capability in the dext. Each rule
replaces a guard that the 1.20 loader does not have.

- Refuse every program and erase request for array 0.
- Refuse a flash row above 255 and an EEPROM row above 127. The dext
  already bounds row checksum requests (`validBootloaderPacket`).
- Write the metadata row last. The loader zeros it at the first write, so
  the new application is valid only when that last write succeeds.
- Verify every written row with row checksum before the metadata row.
