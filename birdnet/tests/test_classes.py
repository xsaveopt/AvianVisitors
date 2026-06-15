import datetime
import unittest

from utils.classes import Detection, ParseFileName

FILE_DATE = datetime.datetime(2024, 2, 24, 16, 19, 37)


class TestDetection(unittest.TestCase):
    def make(self, **kw):
        args = dict(
            file_date=FILE_DATE,
            start_time="3",
            stop_time="6",
            scientific_name="Pica pica",
            common_name="Eurasian Magpie",
            confidence="0.91234",
        )
        args.update(kw)
        return Detection(**args)

    def test_times_offset_from_start(self):
        d = self.make()
        self.assertEqual(d.start, 3.0)
        self.assertEqual(d.stop, 6.0)
        self.assertEqual(d.datetime, datetime.datetime(2024, 2, 24, 16, 19, 40))
        self.assertEqual(d.date, "2024-02-24")
        self.assertEqual(d.time, "16:19:40")

    def test_confidence_rounding(self):
        d = self.make(confidence="0.91234")
        self.assertEqual(d.confidence, 0.9123)
        self.assertEqual(d.confidence_pct, 91)

    def test_confidence_pct_rounds_half(self):
        self.assertEqual(self.make(confidence="0.0").confidence_pct, 0)
        self.assertEqual(self.make(confidence="1.0").confidence_pct, 100)

    def test_week_is_iso_week(self):
        self.assertEqual(self.make().week, 8)

    def test_species_aliases_scientific_name(self):
        d = self.make()
        self.assertEqual(d.species, "Pica pica")
        self.assertEqual(d.scientific_name, "Pica pica")

    def test_common_name_safe_strips_apostrophes_and_spaces(self):
        d = self.make(common_name="Anna's Hummingbird")
        self.assertEqual(d.common_name_safe, "Annas_Hummingbird")

    def test_file_name_extr_defaults_none(self):
        self.assertIsNone(self.make().file_name_extr)

    def test_str_contains_key_fields(self):
        s = str(self.make())
        self.assertIn("Pica pica", s)
        self.assertIn("Eurasian Magpie", s)


class TestParseFileName(unittest.TestCase):
    def test_parses_date_and_time(self):
        p = ParseFileName("/recs/2024-02-24-birdnet-16:19:37.wav")
        self.assertEqual(p.file_date, FILE_DATE)
        self.assertEqual(p.root, "2024-02-24-birdnet-16:19:37")
        self.assertEqual(p.week, 8)

    def test_no_rtsp_id_is_empty_string(self):
        p = ParseFileName("/recs/2024-02-24-birdnet-16:19:37.wav")
        self.assertEqual(p.RTSP_id, "")

    def test_rtsp_id_extracted_from_path(self):
        p = ParseFileName("/recs/RTSP_12-/2024-02-24-birdnet-16:19:37.wav")
        self.assertEqual(p.RTSP_id, "RTSP_12-")

    def test_iso8601_keeps_wall_time(self):
        p = ParseFileName("/recs/2024-02-24-birdnet-16:19:37.wav")
        self.assertIn("2024-02-24T16:19:37", p.iso8601)

    def test_bad_filename_raises(self):
        with self.assertRaises(AttributeError):
            ParseFileName("/recs/not-a-recording.wav")


if __name__ == "__main__":
    unittest.main()
