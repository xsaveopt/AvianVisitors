import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import build_masks

DIMS = {"pica-pica": [560, 420], "parus-major": [400, 560]}
MASKS = {"pica-pica": {"w": 93, "h": 70, "bits": "AAA="}, "parus-major": {"w": 66, "h": 93, "bits": "AQA="}}


class TestConstants(unittest.TestCase):
    def test_the_collage_sizes_are_the_ones_the_app_decodes(self):
        self.assertEqual((build_masks.DIM_MAX, build_masks.MASK_MAX, build_masks.ALPHA_ON), (560, 93, 127))


class MainTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.illus = self.root / "illustrations"
        self.illus.mkdir()
        self.data = self.root / "data"

    def run_main(self, tables=(DIMS, MASKS), extra=()):
        argv = ["build_masks.py", "--illustrations", str(self.illus), "--data", str(self.data), *extra]
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(build_masks, "build_tables", return_value=tables),
            patch.object(sys, "argv", argv),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            code = build_masks.main()
        return code, out.getvalue(), err.getvalue()


class TestWrite(MainTestCase):
    def test_writes_both_tables_and_creates_the_directory(self):
        code, out, _err = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((self.data / "dims.json").read_text()), DIMS)
        self.assertEqual(json.loads((self.data / "masks.json").read_text()), MASKS)
        self.assertIn("built 2 masks", out)
        self.assertIn("bump IMG_VERSION", out)

    def test_the_json_is_written_without_padding(self):
        self.run_main()
        self.assertNotIn(" ", (self.data / "dims.json").read_text())

    def test_an_empty_build_is_an_error(self):
        code, _out, err = self.run_main(tables=({}, {}))
        self.assertEqual(code, 1)
        self.assertIn("no cutouts found", err)
        self.assertFalse(self.data.exists())

    def test_it_reads_the_directory_it_was_given(self):
        with patch.object(build_masks, "build_tables", return_value=(DIMS, MASKS)) as build:
            with patch.object(sys, "argv", ["build_masks.py", "--illustrations", str(self.illus), "--data", str(self.data)]), redirect_stdout(io.StringIO()):
                build_masks.main()
        self.assertEqual(build.call_args[0][0], self.illus)

    def test_an_existing_file_is_replaced(self):
        self.data.mkdir()
        (self.data / "dims.json").write_text('{"stale":[1,1]}')
        self.run_main()
        self.assertEqual(json.loads((self.data / "dims.json").read_text()), DIMS)


class TestCheck(MainTestCase):
    def check(self, current=None):
        if current is not None:
            self.data.mkdir(parents=True, exist_ok=True)
            (self.data / "dims.json").write_text(json.dumps(current))
        return self.run_main(extra=["--check"])

    def test_writes_nothing(self):
        code, _out, _err = self.check()
        self.assertEqual(code, 0)
        self.assertFalse((self.data / "dims.json").exists())

    def test_everything_is_new_without_existing_data(self):
        _code, out, _err = self.check()
        self.assertIn("data currently has 0 entries; +2 new, -0 removed", out)
        self.assertIn("new: parus-major, pica-pica", out)

    def test_reports_additions_and_removals(self):
        _code, out, _err = self.check({"pica-pica": [1, 1], "turdus-merula": [1, 1]})
        self.assertIn("+1 new, -1 removed", out)
        self.assertIn("new: parus-major", out)
        self.assertIn("gone: turdus-merula", out)

    def test_an_unchanged_set_lists_neither(self):
        _code, out, _err = self.check({"pica-pica": [1, 1], "parus-major": [1, 1]})
        self.assertIn("+0 new, -0 removed", out)
        self.assertNotIn("new:", out)
        self.assertNotIn("gone:", out)

    def test_long_lists_are_truncated(self):
        many = {f"bird-{i}": {"w": 1, "h": 1, "bits": ""} for i in range(12)}
        with patch.object(build_masks, "build_tables", return_value=({k: [1, 1] for k in many}, many)):
            with patch.object(sys, "argv", ["build_masks.py", "--illustrations", str(self.illus), "--data", str(self.data), "--check"]):
                out = io.StringIO()
                with redirect_stdout(out):
                    build_masks.main()
        line = next(ln for ln in out.getvalue().splitlines() if "new:" in ln)
        self.assertTrue(line.endswith("..."))
        self.assertEqual(line.count(","), 7)


if __name__ == "__main__":
    unittest.main()
