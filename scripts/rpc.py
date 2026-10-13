"""A JSON-RPC client for ensemble-control.

When ensemble-control restarts, the client reconnects and repeats the call,
so every call that it sends must be safe to repeat. Load it with
runpy.run_path, like the other scripts that share code.
"""
import asyncio
import json

import websockets

URL = "ws://127.0.0.1:8738"


class Client:
    """Reports that arrive before a reply queue for the next notifications("report") read."""

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

    async def notifications(self, method, seconds):
        """Returns the params of each notification of method for the next seconds."""
        found = list(self.reports) if method == "report" else []
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
