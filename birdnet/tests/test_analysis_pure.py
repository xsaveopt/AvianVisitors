import os
import tempfile
import unittest

import numpy as np

from utils.analysis import loadCustomSpeciesList, splitSignal


class TestLoadCustomSpeciesList(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        self.assertEqual(loadCustomSpeciesList("/no/such/file.txt"), [])

    def test_reads_scientific_part_before_underscore(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("Pica pica_Eurasian Magpie\nCorvus corax_Common Raven\n")
            path = f.name
        self.addCleanup(os.unlink, path)
        self.assertEqual(loadCustomSpeciesList(path), ["Pica pica", "Corvus corax"])


class TestSplitSignal(unittest.TestCase):
    def test_pads_short_final_chunk(self):
        rate = 10
        sig = np.arange(75, dtype="float32")
        chunks = splitSignal(sig, rate, overlap=0.0, seconds=3.0, minlen=1.5)
        self.assertEqual(len(chunks), 3)
        for chunk in chunks:
            self.assertEqual(len(chunk), int(3.0 * rate))
        self.assertTrue(np.all(chunks[-1][15:] == 0))

    def test_drops_final_chunk_below_minlen(self):
        rate = 10
        sig = np.arange(65, dtype="float32")
        chunks = splitSignal(sig, rate, overlap=0.0, seconds=3.0, minlen=1.5)
        self.assertEqual(len(chunks), 2)

    def test_overlap_increases_chunk_count(self):
        rate = 10
        sig = np.arange(90, dtype="float32")
        no_overlap = splitSignal(sig, rate, overlap=0.0, seconds=3.0, minlen=1.5)
        with_overlap = splitSignal(sig, rate, overlap=1.0, seconds=3.0, minlen=1.5)
        self.assertGreater(len(with_overlap), len(no_overlap))


if __name__ == "__main__":
    unittest.main()
