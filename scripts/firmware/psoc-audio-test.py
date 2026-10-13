"""Test termination checks in the offline audio emulator."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

from unicorn import UC_ARCH_ARM, UC_MODE_THUMB, Uc

spec = importlib.util.spec_from_file_location(
    "audio_check", Path(__file__).with_name("psoc-audio-check.py")
)
audio_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio_check)


class ExecutionTests(unittest.TestCase):
    def test_refuses_optimized_verification(self):
        result = subprocess.run(
            [sys.executable, "-O", audio_check.__file__, "/nonexistent/flash.bin"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("without Python optimization", result.stderr)
        self.assertNotIn("PASS", result.stdout)

    def setUp(self):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.cpu.mem_map(0x10000, 0x1000)

    def test_returns_result_after_function_return(self):
        self.cpu.mem_write(0x10020, bytes.fromhex("07207047"))
        self.assertEqual(audio_check.call(self.cpu, 0x10020, 0, 0), 7)

    def test_rejects_instruction_limit_without_return(self):
        self.cpu.mem_write(0x10020, bytes.fromhex("0020fee7"))
        with self.assertRaisesRegex(RuntimeError, "did not return"):
            audio_check.call(self.cpu, 0x10020, 0, 0)


if __name__ == "__main__":
    unittest.main()
