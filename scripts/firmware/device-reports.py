"""Read status reports from the Ensemble through ensemble-control.

Usage: python3 scripts/firmware/device-reports.py [--dry-run] [--save DIR]

Every query is a type-3 Get from a fixed allowlist. The tool sends no
command outside that allowlist, so it cannot change device state.
`--save` writes a settings snapshot next to the report result.
"""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

import websockets

URL = "ws://127.0.0.1:8738"
# front-panel-resources.py crc8 over the vendor EnsembleResourceData.bin
VENDOR_RESOURCE_CRC8 = 0x1B

QUERIES = [
    ("psocFirmware", 0x40, 0, 0),
    ("fpgaFirmware", 0x40, 1, 0),
    ("hardwareRevision", 0x40, 2, 0),
    ("resources", 0x40, 3, 0),
    ("unitId", 0x41, 0, 0),
    ("clockLock", 0x42, 0, 0),
    ("pllLock", 0x64, 0, 0),
    ("dspCycleCount", 0xD5, 0, 0),
    ("dspCoreVersion", 0xD2, 0, 0),
]
ALLOWED = {3 | cmd << 8 | p1 << 16 | p2 << 24 for _, cmd, p1, p2 in QUERIES}


def get_words(cmd, p1=0, p2=0):
    word2 = 3 | cmd << 8 | p1 << 16 | p2 << 24
    if word2 not in ALLOWED:
        raise ValueError(f"command {cmd:#x} is outside the allowlist")
    return [1, 0, word2]


def plan():
    return {"queries": [
        {"name": name, "command": cmd, "p1": p1, "words": get_words(cmd, p1, p2)}
        for name, cmd, p1, p2 in QUERIES
    ]}


def decode_versions(report):
    data = report["data"]
    if len(data) < 2:
        return None
    # The host prints each version byte as hexadecimal: 0x56 is "56".
    return ".".join(f"{b:x}" for b in data)


def decode_resource(report):
    data = report["data"]
    if len(data) < 3:
        return None
    return {"version": data[1], "crc8": data[2], "matches_vendor": data[2] == VENDOR_RESOURCE_CRC8}


class Client:
    """A JSON-RPC client. Unmatched replies and reports queue for later reads."""

    def __init__(self, ws):
        self.ws = ws
        self.id = 0
        self.reports = []

    async def send(self, words):
        word2 = words[2] if len(words) > 2 else None
        if words[0:2] != [1, 0] or word2 not in ALLOWED:
            raise ValueError(f"words are outside the allowlist: {words}")
        await self.call("raw.send", {"words": words})
        await asyncio.sleep(0.02)

    async def call(self, method, params=None):
        self.id += 1
        await self.ws.send(json.dumps(
            {"jsonrpc": "2.0", "id": self.id, "method": method, "params": params}))
        while True:
            reply = json.loads(await self.ws.recv())
            if reply.get("id") == self.id:
                if "error" in reply:
                    raise RuntimeError(reply["error"])
                return reply["result"]
            if reply.get("method") == "report":
                self.reports.append(reply["params"])

    async def collect(self, command, seconds=4.0):
        found = [r for r in self.reports if r["command"] == command]
        self.reports = [r for r in self.reports if r["command"] != command]
        deadline = time.monotonic() + seconds
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return found
            try:
                note = json.loads(await asyncio.wait_for(self.ws.recv(), left))
            except asyncio.TimeoutError:
                return found
            if note.get("method") == "report" and note["params"]["command"] == command:
                found.append(note["params"])
            elif note.get("method") == "report":
                self.reports.append(note["params"])


async def read_device(save_dir=None):
    client = Client(await websockets.connect(URL, max_size=None))
    try:
        result = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "reports": {}}
        for name, cmd, p1, p2 in QUERIES:
            await client.send(get_words(cmd, p1, p2))
            found = await client.collect(cmd)
            result["reports"][name] = found[0] if len(found) == 1 else found
        if save_dir:
            snapshot = {"describe": await client.call("describe"),
                        "get": await client.call("get"),
                        "reports": result["reports"]}
            path = save_dir / f"device-snapshot-{time.strftime('%Y%m%d-%H%M%S')}.json"
            path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
            result["snapshot"] = str(path)
        return result
    finally:
        await client.ws.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the query plan and exit")
    parser.add_argument("--save", type=Path, help="directory for the settings snapshot")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(plan(), indent=2))
        return 0
    result = asyncio.run(read_device(args.save))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
