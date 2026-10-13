import unittest

from dsp import Src, block, f32, get, ins, store, transfers


class WireTest(unittest.TestCase):
    def test_block_packs_record_after_header(self):
        self.assertEqual(block(0xD7, 1, 0, [0, 0, 0, 0]), [1, 0, 0x0001D702, 0x00000004, 0])

    def test_get(self):
        self.assertEqual(get(0xD5), [1, 0, 0x0000D503])

    def test_f32(self):
        self.assertEqual(f32(1.0), 0x3F800000)
        self.assertEqual(f32(-0.25), 0xBE800000)


class InstructionTest(unittest.TestCase):
    def test_vendor_words(self):
        self.assertEqual(ins(5, a=3, b=4, b_src=Src.STATE, k=2), 0x490100C5)
        self.assertEqual(ins(4, a=7, b=10, b_src=Src.STATE, k=2, write=True), 0xC90281C4)
        self.assertEqual(ins(5, a=2, b_src=Src.R), 0x42000085)

    def test_store(self):
        self.assertEqual(store(offset=1), 0x00400042)
        self.assertEqual(store(offset=2, out=False, from_x=True), 0x00200082)


class TransferTest(unittest.TestCase):
    def test_short_write_is_first_and_last_chunk(self):
        self.assertEqual(list(transfers(5, 2, [0x0000000B])), [(1, 5, [1, 1, 2, 1, 0x0B, 0, 0, 0])])

    def test_long_write_splits_at_23_words(self):
        chunks = list(transfers(10, 3, list(range(30))))
        self.assertEqual([(p1, p2, data[:4]) for p1, p2, data in chunks],
                         [(23, 10, [1, 0, 3, 30]), (7, 33, [0, 1, 3, 30])])
        self.assertEqual(chunks[1][2][4:8], [23, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
