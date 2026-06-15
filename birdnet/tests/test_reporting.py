import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tests.helpers import Settings
from utils import reporting
from utils.classes import Detection, ParseFileName

FILE_DATE = datetime.datetime(2024, 2, 24, 16, 19, 37)


def settings():
    s = Settings.with_defaults()
    s["RECORDING_LENGTH"] = 15
    return s


def detection():
    return Detection(FILE_DATE, "3", "6", "Pica pica", "Eurasian Magpie", "0.9123")


class TestSummary(unittest.TestCase):
    def test_summary_line(self):
        with patch("utils.reporting.get_settings", return_value=settings()):
            line = reporting.summary(None, detection())
        self.assertEqual(line, "2024-02-24;16:19:40;Pica pica;Eurasian Magpie;0.9123;50;5;0.7;8;1.25;0.0")


class TestJsonFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.wav = os.path.join(self.tmp.name, "2024-02-24-birdnet-16:19:37.wav")
        self.file = ParseFileName(self.wav)

    def test_write_to_json_file(self):
        with patch("utils.reporting.get_settings", return_value=settings()):
            reporting.write_to_json_file(self.file, [detection()])
        data = json.loads(open(self.wav + ".json").read())
        self.assertEqual(data["file_name"], "2024-02-24-birdnet-16:19:37.wav.json")
        self.assertEqual(data["delay"], 15)
        self.assertEqual(len(data["detections"]), 1)
        self.assertEqual(data["detections"][0]["common_name"], "Eurasian Magpie")
        self.assertEqual(data["detections"][0]["start"], 3.0)

    def test_update_removes_stale_json_then_writes(self):
        stale = os.path.join(self.tmp.name, "old.json")
        open(stale, "w").close()
        with patch("utils.reporting.get_settings", return_value=settings()):
            reporting.update_json_file(self.file, [detection()])
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(self.wav + ".json"))


class TestExtractSafe(unittest.TestCase):
    def call(self, start, stop, conf):
        with patch("utils.reporting.get_settings", return_value=conf), patch("utils.reporting.extract") as ex:
            reporting.extract_safe("in.wav", "out.wav", start, stop)
        return ex

    def test_pads_and_clamps(self):
        ex = self.call(0.5, 10, settings())
        ex.assert_called_once_with("in.wav", "out.wav", 0, 11.5)

    def test_clamps_to_recording_length(self):
        ex = self.call(0.5, 20, settings())
        self.assertEqual(ex.call_args.args[3], 15)

    def test_bad_extraction_length_defaults_to_six(self):
        conf = settings()
        conf["EXTRACTION_LENGTH"] = ""
        ex = self.call(5, 5, conf)
        self.assertEqual(ex.call_args.args, ("in.wav", "out.wav", 3.5, 6.5))


if __name__ == "__main__":
    unittest.main()
