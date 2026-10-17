"""Offline tests for the read-only device report client."""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("device-reports.py")
spec = importlib.util.spec_from_file_location("device_reports", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class FakeSocket:
    """Feeds canned messages, then behaves as an idle connection."""

    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []
        self.pending = []

    async def send(self, text):
        message = json.loads(text)
        self.sent.append(message)
        self.pending.append(message["id"])

    async def recv(self):
        await asyncio.sleep(0)
        if self.incoming:
            return json.dumps(self.incoming.pop(0))
        if self.pending:
            return json.dumps({"jsonrpc": "2.0", "id": self.pending.pop(0), "result": True})
        await asyncio.sleep(0.05)
        raise TimeoutError

    async def close(self):
        pass


class GetWordsTest(unittest.TestCase):
    def test_get_encodes_type_three_with_selector(self):
        self.assertEqual(tool.get_words(0x40, 1), [1, 0, 3 | 0x40 << 8 | 1 << 16])
        self.assertEqual(tool.get_words(0xD5), [1, 0, 0x0000D503])

    def test_get_rejects_commands_outside_the_allowlist(self):
        with self.assertRaisesRegex(ValueError, "allowlist"):
            tool.get_words(0x00)


class DecodeTest(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(tool.decode_versions({"p1": 0, "data": [1, 5, 3]}), "1.5.3")
        self.assertEqual(tool.decode_versions({"p1": 1, "data": [0, 0x56, 0]}), "0.56.0")

    def test_resource_crc_verdict(self):
        match = {"p1": 3, "data": [0, 6, 0x1B]}
        mismatch = {"p1": 3, "data": [0, 6, 0x1C]}
        short = {"p1": 3, "data": [0, 6]}
        self.assertEqual(tool.decode_resource(match), {"version": 6, "crc8": 0x1B, "matches_vendor": True})
        self.assertEqual(tool.decode_resource(mismatch)["matches_vendor"], False)
        self.assertIsNone(tool.decode_resource(short))


class PlanTest(unittest.TestCase):
    def test_dry_run_lists_queries_without_a_socket(self):
        plan = tool.plan()
        self.assertEqual(len(plan["queries"]), 9)
        self.assertTrue(all(q["words"][0:2] == [1, 0] for q in plan["queries"]))
        self.assertIn((0x40, 3), [(q["command"], q["p1"]) for q in plan["queries"]])


class GetAllTest(unittest.TestCase):
    def test_get_all_is_a_three_word_type_four_message(self):
        self.assertEqual(tool.GET_ALL, [1, 0, 4])

    def test_send_allows_get_all_but_not_arbitrary_words(self):
        client = tool.Client(FakeSocket([]))
        asyncio.run(client.send(tool.GET_ALL))
        with self.assertRaisesRegex(ValueError, "allowlist"):
            asyncio.run(client.send([1, 0, 0x00000003]))

    def test_get_all_records_every_report(self):
        replies = [
            {"method": "report", "params": {"command": 0x40, "p1": 0, "data": [1, 5, 3]}},
            {"method": "report", "params": {"command": 0x42, "p1": 0, "data": [1]}},
        ]
        client = tool.Client(FakeSocket(replies))
        reports = asyncio.run(client.get_all(seconds=0.05))
        self.assertEqual(sorted(r["command"] for r in reports), [0x40, 0x42])

    def test_logger_records_every_notification(self):
        notes = [
            {"method": "report", "params": {"command": 0x2A, "p1": 0, "data": [0]}},
            {"method": "meters", "params": {"inputs": [0]}},
            {"jsonrpc": "2.0", "id": 1, "result": True},
        ]
        client = tool.Client(FakeSocket(notes))
        events = asyncio.run(client.log_events(0.05))
        self.assertEqual([e["method"] for e in events], ["report", "meters"])


if __name__ == "__main__":
    unittest.main()
