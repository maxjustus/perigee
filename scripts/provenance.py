"""Paths and SHA-256 hashes of the vendor files and derived images.

docs/firmware/provenance.json records them. Load this file with
runpy.run_path, like the other scripts that share code.
"""
import json
from pathlib import Path

RECORD = json.loads((Path(__file__).parents[1] / "docs" / "firmware" / "provenance.json").read_text())
FILES = RECORD["source_files"] + RECORD["analysis"]["derived_files"]


def path(part):
    """Returns the path of the one recorded file whose path contains part."""
    return Path(find(part)["path"])


def sha256(part):
    return find(part)["sha256"]


def find(part):
    [match] = [file for file in FILES if part in file["path"]]
    return match
