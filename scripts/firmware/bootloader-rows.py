"""Compare a bootloader scan with the vendor CYACD, without device access.

`ensemble-bootloader scan --json FILE` writes the scan. Each row checksum is
the loader's 8-bit sum of the row, negated. With ECC off, the sum also covers
the 32 configuration bytes of the row. The loader leaves the metadata active
and verified bytes out of the sum, and the CYACD holds zero in both.
The report-size reply is recorded, not checked: the v1.20 loader on the unit
does not answer as the 1.60 reference does.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

VENDOR = Path(
    "/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/"
    "EnsemblePSoC.cyacd"
)
# 0x2E12F069, sent as a little-endian word.
SILICON_ID = bytes.fromhex("69f0122e")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scan", type=Path)
    parser.add_argument("--image", type=Path, default=VENDOR)
    args = parser.parse_args()
    try:
        result = compare(json.loads(args.scan.read_text()), args.image.read_bytes())
    except (OSError, ValueError, KeyError, IndexError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


def compare(scan, raw):
    rows, _ = inspector().parse(raw)
    device = {
        array * 256 + row: value
        for array, values in enumerate(scan["flash"])
        for row, value in enumerate(values)
    }
    full = {index: (-sum(data)) & 255 for index, data in rows.items()}
    main = {index: (-sum(data[:256])) & 255 for index, data in rows.items()}
    with_config = [index for index in rows if device[index] == full[index]]
    without_config = [index for index in rows if device[index] == main[index]]
    checks = {
        "silicon_id": bytes(scan["identity"][:4]) == SILICON_ID,
        "image_rows_match": len(rows) in (len(with_config), len(without_config)),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "identity_hex": bytes(scan["identity"]).hex(" "),
        "sizes": scan["sizes"],
        "loader_fingerprint_sha256": hashlib.sha256(
            bytes(scan["flash"][0])
        ).hexdigest(),
        "image_rows": len(rows),
        "matched_with_config_bytes": len(with_config),
        "matched_without_config_bytes": len(without_config),
        "mismatched_rows": [
            list(divmod(index, 256))
            for index in sorted(rows)
            if device[index] not in (full[index], main[index])
        ],
    }


def inspector():
    spec = importlib.util.spec_from_file_location(
        "image_format_inspect", Path(__file__).with_name("image-format-inspect.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    sys.exit(main())
