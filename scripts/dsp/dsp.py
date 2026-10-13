"""Probe the Ensemble DSP core through ensemble-control.

NOTES-vendor-driver.md section 8 describes the core and its commands.
`python3 scripts/dsp/dsp.py` prints the cycle count and the core version.
`python3 scripts/dsp/dsp.py restore` cleans up after an interrupted session.
An experiment opens a session, loads a program, routes a rack, and records:

    async with session({"mixers/1/channels/9/mute": False}) as core:
        await core.load([0x0000000B, 0x42000085, 0x00400042], [1, 0, 1, 0])
        await core.route(8)
        dry, mix = record([8, 30])

A session mutes the speaker output. On exit it removes all routes, erases
the core, and restores every setting that it changed. It keeps the old
values in RESTORE_FILE until then, because a service restart ends a session
without its cleanup.
"""
import asyncio
import contextlib
import enum
import json
import pathlib
import struct
import subprocess
import sys

import numpy as np
import websockets

URL = "ws://127.0.0.1:8738"
CODE, COEF, STATE = 0, 1, 2
THREADS = 16
RACKS = 30
CHUNK_WORDS = 23
PROTECT = {"outputs/speaker/mute": True}
RESTORE_FILE = pathlib.Path("/tmp/ensemble-dsp-restore.json")


@contextlib.asynccontextmanager
async def session(changes=None):
    changes = {**PROTECT, **(changes or {})}
    if RESTORE_FILE.exists():
        raise RuntimeError(f"{RESTORE_FILE} exists: run `python3 dsp.py restore` first")
    core = await Core.connect()
    before = await core.call("get")
    RESTORE_FILE.write_text(json.dumps({path: before[path] for path in changes}))
    await core.call("set", changes)
    try:
        yield core
    finally:
        await restore(core)
        await core.ws.close()


async def restore(core):
    for rack in range(RACKS):
        await core.route(rack, on=False)
    await core.erase_all()
    await core.call("set", json.loads(RESTORE_FILE.read_text()))
    RESTORE_FILE.unlink()


class Core:
    """A JSON-RPC client. When ensemble-control restarts, it reconnects and
    repeats the call. Every command that it sends is safe to repeat."""

    def __init__(self, ws):
        self.ws = ws
        self.id = 0
        self.reports = []

    @classmethod
    async def connect(cls):
        return cls(await websockets.connect(URL, max_size=None))

    async def reconnect(self):
        for _ in range(60):
            await asyncio.sleep(0.5)
            try:
                self.ws = await websockets.connect(URL, max_size=None)
                return
            except OSError:
                pass
        raise RuntimeError("ensemble-control did not come back in 30 s")

    async def call(self, method, params=None):
        self.id += 1
        while True:
            try:
                return await self.exchange(method, params)
            except websockets.ConnectionClosed:
                await self.reconnect()

    async def exchange(self, method, params):
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": self.id, "method": method, "params": params}))
        while True:
            reply = json.loads(await self.ws.recv())
            if reply.get("id") == self.id:
                if "error" in reply:
                    raise RuntimeError(reply["error"])
                return reply["result"]
            if reply.get("method") == "report":
                self.reports.append(reply["params"])

    async def send(self, words):
        await self.call("raw.send", {"words": words})
        # The dext drops messages when its 32-entry outbox is full.
        await asyncio.sleep(0.02)

    async def notifications(self, method, seconds):
        found = [r for r in self.reports if method == "report"]
        self.reports.clear()
        loop = asyncio.get_running_loop()
        end = loop.time() + seconds
        while (left := end - loop.time()) > 0:
            try:
                note = json.loads(await asyncio.wait_for(self.ws.recv(), left))
            except asyncio.TimeoutError:
                break
            except websockets.ConnectionClosed:
                await self.reconnect()
                continue
            if note.get("method") == method:
                found.append(note["params"])
        return found

    async def query(self, command, seconds=4.0):
        await self.send(get(command))
        return [r["data"] for r in await self.notifications("report", seconds) if r["command"] == command]

    async def input_peaks(self, seconds=1.0):
        frames = await self.notifications("meters", seconds)
        return [max(f["inputs"][i] for f in frames) for i in range(30)]

    async def erase_all(self):
        for thread in range(THREADS):
            for memory in (CODE, STATE, COEF):
                await self.send(block(0xD6, memory, 0, [1, 1, thread, 0xFF]))

    async def halt(self, start, thread, count):
        await self.send(block(0xD7, 0, start, [0, 0, thread, count]))

    async def resume_all(self):
        await self.send(block(0xD7, 1, 0, [0, 0, 0, 0]))

    async def write(self, command, start, thread, words):
        for p1, p2, data in transfers(start, thread, words):
            await self.send(block(command, p1, p2, data))

    async def code(self, words, start=0, thread=0):
        await self.write(0xD0, start, thread, words)

    async def coefs(self, values, start=0, thread=0):
        await self.write(0xD1, start, thread, [f32(v) for v in values])

    async def state(self, values, start=0, thread=0):
        await self.write(0xD4, start, thread, [f32(v) for v in values])

    async def swap(self, code, length=32, thread=0):
        """Replaces the program at address 0. Zero words pad it, so no old word runs."""
        await self.halt(0, thread, length)
        await self.code(code + [0] * (length - len(code)), thread=thread)
        await self.resume_all()

    async def load(self, code, coefs, state=(), thread=0):
        """Loads one program at address 0 of a thread, as FXFragment::load does."""
        await self.erase_all()
        await self.halt(0, thread, len(code))
        await self.code(code, thread=thread)
        if state:
            await self.state(state, thread=thread)
        await self.coefs(coefs, thread=thread)
        await self.resume_all()

    async def route(self, rack, io=0, on=True):
        await self.send(block(0xD3, rack, 0, [io, io, int(on)]))


class Src(enum.IntEnum):
    """Operand select. For operand B, COEF selects zero."""
    COEF = 0
    STATE = 1
    R = 2
    X = 3


def ins(op, a=0, a_src=Src.COEF, b=0, b_src=Src.COEF, k=0, to_r=True, write=False):
    """Encodes an arithmetic instruction. k sets a 2^k-word circular group."""
    return (op | a << 6 | b << 14 | a_src << 22 | b_src << 24 | k << 26
            | int(to_r) << 30 | int(write) << 31)


def store(offset=0, io=0, out=True, from_x=False, mode=0):
    """Encodes opcode 0x02: r or x to a state word and, with out, to a DSP I/O channel."""
    return 2 | offset << 6 | mode << 18 | int(from_x) << 21 | int(out) << 22 | io << 23


def f32(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def message(record):
    """Prefixes a PSoC record with the 2-word header and packs it into words."""
    record = list(record) + [0] * (-len(record) % 4)
    return [1, 0] + [int.from_bytes(bytes(record[i:i + 4]), "little") for i in range(0, len(record), 4)]


def block(command, p1, p2, data):
    return message([2, command, p1, p2, len(data), *data])


def get(command, p1=0, p2=0):
    return message([3, command, p1, p2])


def transfers(start, thread, words):
    """Splits a code, coefficient, or state write into (p1, p2, data) chunks."""
    for at in range(0, len(words), CHUNK_WORDS):
        chunk = words[at:at + CHUNK_WORDS]
        flags = [int(at == 0), int(at + CHUNK_WORDS >= len(words)), thread, len(words)]
        yield len(chunk), start + at, flags + list(struct.pack(f"<{len(chunk)}I", *chunk))


CAPTURE = pathlib.Path(__file__).with_name("capture.swift")
CAPTURE_BINARY = pathlib.Path("/tmp/ensemble-dsp-capture")


def record(channels, seconds=1.2, settle=4800):
    """Records record-stream channels. Returns one array per channel."""
    if not CAPTURE_BINARY.exists() or CAPTURE_BINARY.stat().st_mtime < CAPTURE.stat().st_mtime:
        subprocess.run(["swiftc", "-O", "-o", CAPTURE_BINARY, CAPTURE], check=True)
    raw = subprocess.run([CAPTURE_BINARY, str(seconds), *map(str, channels)], check=True,
                         capture_output=True).stdout
    return np.frombuffer(raw, "<f4").reshape(-1, len(channels)).T[:, settle:]


def gain(dry, wet, lags=range(-8, 9)):
    """Fits wet = gain * dry delayed by lag. Returns (lag, gain, residual rms)."""
    n = min(len(dry), len(wet)) - 2 * max(map(abs, lags))
    edge = max(map(abs, lags))
    fits = []
    for lag in lags:
        x, y = dry[edge:edge + n], wet[edge + lag:edge + lag + n]
        g = x @ y / (x @ x)
        fits.append((lag, g, float(np.sqrt(np.mean((y - g * x) ** 2)))))
    return min(fits, key=lambda fit: fit[2])


def response(dry, wet, taps=range(-4, 12)):
    """Fits wet as an FIR filter of dry. Returns the taps."""
    edge = max(map(abs, taps))
    n = min(len(dry), len(wet)) - 2 * edge
    x = np.stack([dry[edge - k:edge - k + n] for k in taps], axis=1)
    return np.linalg.lstsq(x, wet[edge:edge + n], rcond=None)[0]


async def main(command):
    core = await Core.connect()
    if command == "restore":
        await restore(core)
    else:
        print("cycles per thread and sample:", await core.query(0xD5))
        print("core version:", await core.query(0xD2))
    await core.ws.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
