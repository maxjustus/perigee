"""Compare the Ensemble and Element PSoC firmware images offline.

Usage: python3 scripts/firmware/cross-model-compare.py

Both products use the same silicon, the same 64 KB loader boundary, and
the same record format. This tool measures which application regions are
byte-identical across the two models, maps changed regions onto the
Ensemble function map, and reports the split between shared vendor logic
and model-specific logic.
"""

import csv
import json
import sys
from pathlib import Path

FLASH_START = 0x10000
FLASH_END = 0x40000
METADATA_ROW = 1023


def parse(raw):
    lines = raw.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    header = lines[0].decode("ascii")
    rows = {}
    for line in lines[1:]:
        body = bytes.fromhex(line[1:].decode("ascii"))
        assert len(body) == int.from_bytes(body[3:5], "big") + 6
        assert sum(body) & 0xFF == 0, "row checksum"
        index = body[0] * 256 + int.from_bytes(body[1:3], "big")
        assert len(body[5:-1]) == 288, "row geometry"
        rows[index] = body[5:-1]
    return header, rows


def flash_image(rows, start, end):
    image = bytearray(b"\xff" * (end - start))
    for index, payload in rows.items():
        if start <= index * 256 < end:
            base = index * 256 - start
            image[base:base + 256] = payload[:256]
    return bytes(image)


def row_diff(ensemble, element):
    keys_e = {k for k in ensemble if k != METADATA_ROW}
    keys_l = {k for k in element if k != METADATA_ROW}
    overlap = keys_e & keys_l
    return {
        "identical": sorted(k for k in overlap if ensemble[k] == element[k]),
        "changed": sorted(k for k in overlap if ensemble[k] != element[k]),
        "ensemble_only": sorted(keys_e - keys_l),
        "element_only": sorted(keys_l - keys_e),
        "identical_count": 0,
        "changed_count": 0,
        "overlap_count": len(overlap),
    }


def function_report(flash_ensemble, flash_element, offset, functions):
    identical, changed = [], []
    for entry, size, name in functions:
        start, end = entry - offset, entry + size - offset
        if flash_ensemble[start:end] == flash_element[start:end]:
            identical.append((name, entry))
        else:
            changed.append((name, entry))
    covered = set()
    for entry, size, _ in functions:
        covered.update(range(entry, entry + size))
    uncovered = [
        address
        for address in range(len(flash_ensemble))
        if flash_ensemble[address] != flash_element[address]
        and address not in covered
    ]
    return {
        "identical": identical,
        "changed": changed,
        "uncovered_changed_bytes": len(uncovered),
        "uncovered_ranges": byte_ranges(uncovered),
    }


def byte_ranges(addresses):
    ranges = []
    for address in addresses:
        if ranges and address == ranges[-1][1]:
            ranges[-1][1] = address + 1
        else:
            ranges.append([address, address + 1])
    return [[start, end] for start, end in ranges]


def named_functions():
    names = {}
    for path in sorted(Path("docs/firmware/names").glob("*.tsv")):
        with path.open() as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if "kind" not in (reader.fieldnames or []):
                continue  # host-address namespaces, e.g. updater.tsv
            for row in reader:
                if row["kind"] == "function":
                    names.setdefault(int(row["address"], 0), row["name"])
    functions = []
    for row in csv.DictReader(Path("/tmp/apogee-fw/functions.tsv").open(), delimiter="\t"):
        entry = int(row["entry"], 16)
        functions.append((entry, int(row["bytes"]), names.get(entry, row["name"])))
    return sorted(functions)


def moved_functions(flash_ensemble, flash_element, functions, offset):
    """Find Ensemble function bodies reproduced exactly elsewhere in the
    Element build, at a different address. Skip padding-like bodies, which
    match the erased fill everywhere."""
    moved = []
    for entry, size, name in functions:
        body = flash_ensemble[entry - offset:entry + size - offset]
        if size < 8 or body.count(0xFF) > size * 9 // 10:
            continue
        index = flash_element.find(body)
        if index >= 0 and index != entry - offset:
            moved.append((name, entry, index + offset))
    return moved


def compare(ensemble, element):
    rows = row_diff(ensemble[1], element[1])
    rows["identical_count"] = len(rows["identical"])
    rows["changed_count"] = len(rows["changed"])
    flash_e = flash_image(ensemble[1], FLASH_START, FLASH_END)
    flash_l = flash_image(element[1], FLASH_START, FLASH_END)
    functions = named_functions()
    report = {
        "ensemble_length": int.from_bytes(
            ensemble[1][METADATA_ROW][201:205], "little"),
        "element_length": int.from_bytes(
            element[1][METADATA_ROW][201:205], "little"),
        "row_overlap": rows,
        "functions": None,
        "function_total": len(functions),
    }
    parts = function_report(flash_e, flash_l, FLASH_START, functions)
    report["functions"] = {
        "identical_count": len(parts["identical"]),
        "changed_count": len(parts["changed"]),
        "uncovered_changed_bytes": parts["uncovered_changed_bytes"],
        "uncovered_ranges": parts["uncovered_ranges"],
    }
    report["moved"] = moved_functions(flash_e, flash_l, functions, FLASH_START)
    report["moved_count"] = len(report["moved"])
    return report, parts


def main():
    resources = Path(
        "/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources"
    )
    report, parts = compare(
        parse((resources / "EnsemblePSoC.cyacd").read_bytes()),
        parse((resources / "Element.cyacd").read_bytes()),
    )
    print(json.dumps(report, indent=2))
    print("\nchanged functions:")
    for name, entry in parts["changed"]:
        print(f"  {name} @ {entry:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
