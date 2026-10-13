"""Inspect the Ensemble single-app CYACD profile, without device access.

Only the observed silicon header, 256+32 byte rows, fixed app origin,
and row-aligned app lengths are supported. Success proves neither firmware
correctness nor compatibility with the absent bootloader.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.image.read_bytes())
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def inspect(raw):
    rows, offsets = parse(raw)
    if 1023 not in rows:
        raise ValueError("metadata row absent")
    metadata = rows[1023][192:256]
    fields = {
        "checksum": metadata[0],
        "entry_point": int.from_bytes(metadata[1:5], "little"),
        "bootloader_last_row": int.from_bytes(metadata[5:7], "little"),
        "length": int.from_bytes(metadata[9:13], "little"),
        "run_type": metadata[13],
        "active": metadata[16],
        "verified": metadata[17],
        "bootloader_version": int.from_bytes(metadata[18:20], "little"),
        "application_id": int.from_bytes(metadata[20:22], "little"),
        "application_version": int.from_bytes(metadata[22:24], "little"),
        "customer_id": int.from_bytes(metadata[24:28], "little"),
    }
    length = fields["length"]
    if fields["bootloader_last_row"] != 255:
        raise ValueError("unsupported bootloader boundary")
    if not 0 < length <= 0x2FF00 or length % 256:
        raise ValueError("unsupported application length or metadata overlap")
    start, end = 0x10000, 0x10000 + length
    expected = set(range(start // 256, end // 256)) | {1023}
    if set(rows) != expected:
        raise ValueError("application row coverage differs from metadata")
    entry = fields["entry_point"]
    if not entry & 1 or not start <= (entry & ~1) < end:
        raise ValueError("entry point is not a Thumb address within the application")
    if int.from_bytes(rows[256][4:8], "little") != entry:
        raise ValueError("entry point differs from the reset vector")
    flash_sum = sum(sum(rows[row][:256]) for row in expected - {1023}) & 255
    config_sum = sum(sum(rows[row][256:]) for row in expected - {1023}) & 255
    checksum = (-(flash_sum + config_sum)) & 255
    if checksum != fields["checksum"]:
        raise ValueError("application checksum mismatch, with config bytes included")
    arrays = {}
    for index in rows:
        array, row = divmod(index, 256)
        bounds = arrays.setdefault(str(array), [row, row, 0])
        bounds[1] = row
        bounds[2] += 1
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "silicon_id": "0x2E12F069",
        "silicon_revision": 0,
        "packet_checksum_type": 0,
        "row_count": len(rows),
        "arrays": arrays,
        "row_checksums_match": True,
        "app_start": start,
        "app_end_exclusive": end,
        "config_start": 0x48000000 + start // 8,
        "config_end_exclusive": 0x48000000 + end // 8,
        "flash_sum8": flash_sum,
        "config_sum8": config_sum,
        "app_checksum": checksum,
        "metadata_file_offset": offsets[1023] + 11 + 2 * 192,
        "metadata": fields,
        "metadata_hex": metadata.hex(),
        "metadata_row_prefix_hex": rows[1023][:192].hex(),
        "metadata_config_hex": rows[1023][256:].hex(),
        "limitation": "Checksum agreement is not proof of correct, bootable, or safe firmware. "
                      "The bootloader and device state are absent. Metadata is outside the app checksum.",
    }


def parse(raw):
    lines = raw.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    if not lines:
        raise ValueError("empty image")
    header = decode_hex(lines[0].removesuffix(b"\r"), 1)
    if header != bytes.fromhex("2E12F0690000"):
        raise ValueError("unsupported silicon header, revision, or packet checksum type")
    rows, offsets = {}, {}
    offset = len(lines[0]) + 1
    previous = -1
    for number, line in enumerate(lines[1:], 2):
        text = line.removesuffix(b"\r")
        if not text.startswith(b":"):
            raise ValueError(f"line {number}: absent row colon")
        body = decode_hex(text[1:], number)
        if len(body) < 6 or len(body) != int.from_bytes(body[3:5], "big") + 6:
            raise ValueError(f"line {number}: row length mismatch")
        if sum(body) & 255:
            raise ValueError(f"line {number}: row checksum mismatch")
        array, row = body[0], int.from_bytes(body[1:3], "big")
        if not 1 <= array <= 3 or row > 255 or len(body) != 294:
            raise ValueError(f"line {number}: unsupported array, row, or geometry")
        index = array * 256 + row
        if index <= previous:
            raise ValueError(f"line {number}: duplicate row or noncanonical order")
        previous = index
        rows[index], offsets[index] = body[5:-1], offset
        offset += len(line) + 1
    return rows, offsets


def decode_hex(text, number):
    if not re.fullmatch(rb"(?:[0-9a-fA-F]{2})+", text):
        raise ValueError(f"line {number}: expected hexadecimal byte pairs")
    return bytes.fromhex(text.decode("ascii"))


if __name__ == "__main__":
    sys.exit(main())
