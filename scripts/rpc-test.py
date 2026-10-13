"""Offline tests for the ensemble-control JSON-RPC client."""

import asyncio
import json
from pathlib import Path
import runpy
import unittest

Client = runpy.run_path(str(Path(__file__).with_name("rpc.py")))["Client"]


class ClientTest(unittest.TestCase):
    def test_call_returns_result_and_queues_reports(self):
        response = {"jsonrpc": "2.0", "id": 1, "result": {"clock/sampleRate": "48000"}}
        report = {"method": "report", "params": {"command": 0x40, "p1": 0, "data": [1, 5, 3]}}
        client = Client(FakeSocket([report, response]))
        result = asyncio.run(client.call("get"))
        self.assertEqual(result, {"clock/sampleRate": "48000"})
        self.assertEqual(client.reports[0]["command"], 0x40)

    def test_report_notifications_include_queued_reports(self):
        queued = {"command": 0x40, "p1": 0, "data": [1]}
        meters = {"method": "meters", "params": {"inputs": []}}
        report = {"method": "report", "params": {"command": 0x42, "p1": 0, "data": [1]}}
        client = Client(FakeSocket([meters, report]))
        client.reports.append(queued)
        found = asyncio.run(client.notifications("report", seconds=0.05))
        self.assertEqual(found, [queued, report["params"]])
        self.assertEqual(client.reports, [])


class FakeSocket:
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def recv(self):
        await asyncio.sleep(0)
        if not self.incoming:
            await asyncio.sleep(0.05)
            raise TimeoutError
        return json.dumps(self.incoming.pop(0))


if __name__ == "__main__":
    unittest.main()
