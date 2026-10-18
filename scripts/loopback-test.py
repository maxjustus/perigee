"""Offline tests for the comparison in loopback.py.

Usage: uv run --with numpy python3 scripts/loopback-test.py
"""

from pathlib import Path
import runpy
import unittest

import numpy as np

loopback = runpy.run_path(str(Path(__file__).with_name("loopback.py")))
compare, signal, LEAD = loopback["compare"], loopback["signal"], loopback["LEAD"]


def delayed(samples, lag):
    out = np.zeros_like(samples)
    out[lag:] = samples[:len(samples) - lag]
    return out


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.sent = signal()

    def test_a_delayed_copy_is_exact(self):
        result = compare(self.sent[:, 0], delayed(self.sent[:, 0], 1402))
        self.assertEqual(result, {"lag": 1402, "exact32": 1.0, "max_error": 0, "exact24": 1.0})

    def test_errors_below_24_bits_keep_24_bit_exactness(self):
        result = compare(self.sent[:, 0], delayed(self.sent[:, 0], 300) + 2)
        self.assertEqual((result["exact24"], result["max_error"]), (1.0, 2))
        self.assertLess(result["exact32"], 1.0)

    def test_the_other_side_fails(self):
        result = compare(self.sent[:, 0], delayed(self.sent[:, 1], 300))
        self.assertTrue(result is None or result["exact24"] < 0.01)

    def test_silence_has_no_signal(self):
        self.assertIsNone(compare(self.sent[:, 0], np.zeros_like(self.sent[:, 0])))

    def test_the_noise_starts_after_the_lead(self):
        self.assertEqual(np.flatnonzero(self.sent[:, 0])[0], LEAD)


if __name__ == "__main__":
    unittest.main()
