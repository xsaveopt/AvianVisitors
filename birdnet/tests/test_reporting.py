import datetime
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

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


CREATEDB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "createdb.sh")
FONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts", "RobotoFlex-Regular.ttf")


def schema_sql():
    text = open(CREATEDB).read()
    return re.search(r"<< EOF\n(.*?)\nEOF", text, re.S).group(1)


def stored_detection(extr="/data/Extracted/By_Date/2024-02-24/Eurasian_Magpie/Eurasian_Magpie-91-2024-02-24-birdnet-16:19:40.mp3"):
    d = detection()
    d.file_name_extr = extr
    return d


class TestWriteToDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "birds.db")
        con = sqlite3.connect(self.db)
        con.executescript(schema_sql())
        con.close()
        self.addCleanup(patch.stopall)
        patch("utils.reporting.DB_PATH", self.db).start()
        patch("utils.reporting.get_settings", return_value=settings()).start()
        self.sleep = patch("utils.reporting.sleep").start()

    def rows(self):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute("SELECT * FROM detections")]
        con.close()
        return rows

    def test_insert_matches_createdb_schema(self):
        reporting.write_to_db(None, stored_detection())
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "Date": "2024-02-24",
                "Time": "16:19:40",
                "Sci_Name": "Pica pica",
                "Com_Name": "Eurasian Magpie",
                "Confidence": 0.9123,
                "Lat": 50.0,
                "Lon": 5.0,
                "Cutoff": 0.7,
                "Week": 8,
                "Sens": 1.25,
                "Overlap": 0.0,
                "File_Name": "Eurasian_Magpie-91-2024-02-24-birdnet-16:19:40.mp3",
            },
        )

    def test_insert_value_count_matches_schema_columns(self):
        con = sqlite3.connect(self.db)
        columns = [r[1] for r in con.execute("PRAGMA table_info(detections)")]
        con.close()
        self.assertEqual(len(columns), 12)
        reporting.write_to_db(None, stored_detection())
        self.assertEqual(len(self.rows()), 1)

    def test_retries_after_a_busy_database(self):
        real_connect = sqlite3.connect
        attempts = []

        def flaky(path):
            attempts.append(path)
            if len(attempts) < 3:
                raise sqlite3.OperationalError("database is locked")
            return real_connect(path)

        with patch("utils.reporting.sqlite3.connect", side_effect=flaky):
            reporting.write_to_db(None, stored_detection())
        self.assertEqual(len(attempts), 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.assertEqual(len(self.rows()), 1)

    def test_stops_after_first_success(self):
        with patch("utils.reporting.sqlite3.connect", wraps=sqlite3.connect) as connect:
            reporting.write_to_db(None, stored_detection())
        self.assertEqual(connect.call_count, 1)
        self.sleep.assert_not_called()

    def test_gives_up_after_three_attempts(self):
        with patch("utils.reporting.sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")) as connect:
            reporting.write_to_db(None, stored_detection())
        self.assertEqual(connect.call_count, 3)
        self.assertEqual(self.rows(), [])

    def test_closes_connection_when_insert_fails(self):
        con = MagicMock()
        con.cursor.return_value.execute.side_effect = sqlite3.OperationalError("database is locked")
        with patch("utils.reporting.sqlite3.connect", return_value=con):
            reporting.write_to_db(None, stored_detection())
        self.assertEqual(con.close.call_count, 3)

    def test_dropped_detection_is_logged_as_error(self):
        with patch("utils.reporting.sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")):
            with self.assertLogs("utils.reporting", level="ERROR"):
                reporting.write_to_db(None, stored_detection())


class TestApprise(unittest.TestCase):
    def run_apprise(self, detections, side_effect=None):
        with (
            patch("utils.reporting.get_settings", return_value=settings()),
            patch("utils.reporting.sendAppriseNotifications", side_effect=side_effect) as send,
        ):
            reporting.apprise(None, detections)
        return send

    def make(self, sci, com, start="3", conf="0.9"):
        d = Detection(FILE_DATE, start, str(float(start) + 3), sci, com, conf)
        d.file_name_extr = f"/data/{com}.mp3"
        return d

    def test_one_notification_per_species_per_run(self):
        send = self.run_apprise([self.make("Pica pica", "Eurasian Magpie", "0"), self.make("Pica pica", "Eurasian Magpie", "3")])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0], "Pica pica")
        self.assertEqual(send.call_args.args[4], "Eurasian Magpie.mp3")

    def test_distinct_species_each_notify(self):
        send = self.run_apprise([self.make("Pica pica", "Eurasian Magpie"), self.make("Corvus corax", "Common Raven")])
        self.assertEqual([c.args[0] for c in send.call_args_list], ["Pica pica", "Corvus corax"])

    def test_failure_does_not_stop_other_species(self):
        send = self.run_apprise(
            [self.make("Pica pica", "Eurasian Magpie"), self.make("Pica pica", "Eurasian Magpie"), self.make("Corvus corax", "Common Raven")],
            side_effect=[RuntimeError("boom"), None],
        )
        self.assertEqual([c.args[0] for c in send.call_args_list], ["Pica pica", "Corvus corax"])

    def test_passes_confidence_and_week_as_strings(self):
        send = self.run_apprise([self.make("Pica pica", "Eurasian Magpie", conf="0.9123")])
        args = send.call_args.args
        self.assertEqual(args[2], "0.9123")
        self.assertEqual(args[3], "91")
        self.assertEqual(args[7], "8")


class TestBirdWeather(unittest.TestCase):
    def setUp(self):
        self.conf = settings()
        self.conf["BIRDWEATHER_ID"] = "station-token"
        self.file = ParseFileName("/data/StreamData/2024-02-24-birdnet-16:19:37.wav")
        self.addCleanup(patch.stopall)
        patch("utils.reporting.get_settings", return_value=self.conf).start()
        patch("utils.reporting.soundfile.read", return_value=([0.0, 0.1], 48000)).start()
        patch("utils.reporting.soundfile.write", side_effect=lambda buf, *a, **k: buf.write(b"fLaC")).start()
        self.requests = patch("utils.reporting.requests").start()
        self.requests.post.return_value.status_code = 201
        self.requests.post.return_value.json.return_value = {"success": True, "soundscape": {"id": 42}}

    def test_disabled_without_station_id(self):
        self.conf["BIRDWEATHER_ID"] = ""
        reporting.bird_weather(self.file, [detection()])
        self.requests.post.assert_not_called()

    def test_no_detections_posts_nothing(self):
        reporting.bird_weather(self.file, [])
        self.requests.post.assert_not_called()

    def test_posts_soundscape_then_each_detection(self):
        other = Detection(FILE_DATE, "9", "12", "Corvus corax", "Common Raven", "0.8")
        reporting.bird_weather(self.file, [detection(), other])
        self.assertEqual(self.requests.post.call_count, 3)
        first = self.requests.post.call_args_list[0]
        self.assertEqual(first.kwargs["url"], f"https://app.birdweather.com/api/v1/stations/station-token/soundscapes?timestamp={self.file.iso8601}")
        self.assertEqual(first.kwargs["data"], b"fLaC")
        self.assertEqual(first.kwargs["headers"], {"Content-Type": "audio/flac"})
        det_calls = self.requests.post.call_args_list[1:]
        for c in det_calls:
            self.assertEqual(c.args[0], "https://app.birdweather.com/api/v1/stations/station-token/detections")
            self.assertEqual(c.kwargs["json"]["soundscapeId"], 42)
            self.assertEqual(c.kwargs["json"]["algorithm"], "2p4")
        self.assertEqual([c.kwargs["json"]["scientificName"] for c in det_calls], ["Pica pica", "Corvus corax"])
        self.assertEqual(det_calls[1].kwargs["json"]["soundscapeStartTime"], 9.0)
        self.assertEqual(det_calls[1].kwargs["json"]["soundscapeEndTime"], 12.0)
        self.assertEqual(det_calls[0].kwargs["json"]["lat"], 50)

    def test_other_models_report_alpha_algorithm(self):
        self.conf["MODEL"] = "Perch_v2"
        reporting.bird_weather(self.file, [detection()])
        self.assertEqual(self.requests.post.call_args_list[1].kwargs["json"]["algorithm"], "alpha")

    def test_rejected_soundscape_skips_detections(self):
        self.requests.post.return_value.json.return_value = {"success": False, "message": "bad station"}
        with self.assertLogs("utils.reporting", level="ERROR"):
            reporting.bird_weather(self.file, [detection()])
        self.assertEqual(self.requests.post.call_count, 1)

    def test_soundscape_post_error_is_swallowed(self):
        self.requests.post.side_effect = ConnectionError("offline")
        with self.assertLogs("utils.reporting", level="ERROR"):
            reporting.bird_weather(self.file, [detection()])
        self.assertEqual(self.requests.post.call_count, 1)

    def test_flac_conversion_error_posts_nothing(self):
        with patch("utils.reporting.soundfile.read", side_effect=RuntimeError("unreadable")):
            with self.assertLogs("utils.reporting", level="ERROR"):
                reporting.bird_weather(self.file, [detection()])
        self.requests.post.assert_not_called()

    def test_detection_post_error_continues_with_next(self):
        ok = MagicMock(status_code=201)
        ok.json.return_value = {"success": True, "soundscape": {"id": 7}}
        other = Detection(FILE_DATE, "9", "12", "Corvus corax", "Common Raven", "0.8")
        self.requests.post.side_effect = [ok, ConnectionError("offline"), MagicMock(status_code=201)]
        reporting.bird_weather(self.file, [detection(), other])
        self.assertEqual(self.requests.post.call_count, 3)


class TestHeartbeat(unittest.TestCase):
    def run_heartbeat(self, url, side_effect=None):
        conf = settings()
        conf["HEARTBEAT_URL"] = url
        with patch("utils.reporting.get_settings", return_value=conf), patch("utils.reporting.requests.get", side_effect=side_effect) as get:
            reporting.heartbeat()
        return get

    def test_disabled_without_url(self):
        self.run_heartbeat("").assert_not_called()

    def test_pings_url(self):
        get = self.run_heartbeat("https://heartbeat.example/ping")
        get.assert_called_once_with(url="https://heartbeat.example/ping", timeout=10)

    def test_error_is_swallowed(self):
        with self.assertLogs("utils.reporting", level="ERROR"):
            self.run_heartbeat("https://heartbeat.example/ping", side_effect=ConnectionError("offline"))


class TestExtractDetection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conf = settings()
        self.conf.update({"AUDIOFMT": "mp3", "EXTRACTED": self.tmp.name, "RAW_SPECTROGRAM": "0"})
        self.file = ParseFileName(os.path.join(self.tmp.name, "2024-02-24-birdnet-16:19:37.wav"))
        self.expected = os.path.join(self.tmp.name, "By_Date", "2024-02-24", "Eurasian_Magpie", "Eurasian_Magpie-91-2024-02-24-birdnet-16:19:40.mp3")

    def run_extract(self, det=None):
        with (
            patch("utils.reporting.get_settings", return_value=self.conf),
            patch("utils.reporting.extract_safe") as ex,
            patch("utils.reporting.spectrogram") as spec,
        ):
            out = reporting.extract_detection(self.file, det or detection())
        return out, ex, spec

    def test_extracts_into_dated_species_dir(self):
        out, ex, spec = self.run_extract()
        self.assertEqual(out, self.expected)
        self.assertTrue(os.path.isdir(os.path.dirname(self.expected)))
        ex.assert_called_once_with(self.file.file_name, self.expected, 3.0, 6.0)
        self.assertEqual(spec.call_args.args[0], self.expected)
        self.assertEqual(spec.call_args.args[1], "Eurasian Magpie")
        self.assertEqual(spec.call_args.args[3], "0")

    def test_existing_extraction_is_not_redone(self):
        os.makedirs(os.path.dirname(self.expected))
        open(self.expected, "w").close()
        with self.assertLogs("utils.reporting", level="WARNING"):
            out, ex, spec = self.run_extract()
        self.assertEqual(out, self.expected)
        ex.assert_not_called()
        spec.assert_not_called()

    def test_apostrophes_are_stripped_from_names(self):
        det = Detection(FILE_DATE, "3", "6", "Calypte anna", "Anna's Hummingbird", "0.5")
        out, _, _ = self.run_extract(det)
        self.assertEqual(os.path.basename(out), "Annas_Hummingbird-50-2024-02-24-birdnet-16:19:40.mp3")
        self.assertEqual(os.path.basename(os.path.dirname(out)), "Annas_Hummingbird")

    def test_rtsp_id_is_part_of_the_name(self):
        self.file = ParseFileName(os.path.join(self.tmp.name, "2024-02-24-birdnet-RTSP_2-16:19:37.wav"))
        out, _, _ = self.run_extract()
        self.assertEqual(os.path.basename(out), "Eurasian_Magpie-91-2024-02-24-birdnet-RTSP_2-16:19:40.mp3")


class TestSpectrogram(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audio = os.path.join(self.tmp.name, "clip.mp3")
        self.made = []
        p = patch("utils.reporting.get_font", return_value={"path": FONT})
        p.start()
        self.addCleanup(p.stop)

    def fake_sox(self, stderr=b""):
        def run(args, **kwargs):
            out = args[args.index("-o") + 1]
            self.made.append(out)
            Image.new("RGB", (200, 100)).save(out)
            return subprocess.CompletedProcess(args, 0, b"", stderr)

        return run

    def test_writes_png_next_to_audio(self):
        with patch("utils.reporting.subprocess.run", side_effect=self.fake_sox()) as run:
            reporting.spectrogram(self.audio, "Eurasian Magpie", "comment")
        self.assertTrue(os.path.isfile(self.audio + ".png"))
        self.assertEqual(Image.open(self.audio + ".png").size, (200, 100))
        self.assertNotIn("-r", run.call_args.args[0])
        self.assertFalse(os.path.exists(self.made[0]))

    def test_raw_flag_adds_r(self):
        with patch("utils.reporting.subprocess.run", side_effect=self.fake_sox()) as run:
            reporting.spectrogram(self.audio, "Eurasian Magpie", "comment", raw="1")
        self.assertEqual(run.call_args.args[0][-1], "-r")

    def test_sox_stderr_raises(self):
        with patch("utils.reporting.subprocess.run", side_effect=self.fake_sox(b"sox FAIL")):
            with self.assertRaises(RuntimeError):
                reporting.spectrogram(self.audio, "Eurasian Magpie", "comment")
        self.assertFalse(os.path.exists(self.audio + ".png"))

    def test_temp_file_removed_when_sox_fails(self):
        with patch("utils.reporting.subprocess.run", side_effect=self.fake_sox(b"sox FAIL")):
            with self.assertRaises(RuntimeError):
                reporting.spectrogram(self.audio, "Eurasian Magpie", "comment")
        self.assertFalse(os.path.exists(self.made[0]))


if __name__ == "__main__":
    unittest.main()
