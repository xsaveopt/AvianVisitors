import json
import os
import unittest
from unittest.mock import patch

from utils import helpers


class TestPHPConfigParser(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, helpers, "_settings", None)

    def test_strips_surrounding_quotes_and_keeps_case(self):
        path = os.path.join(self.tmp.name, "birdnet.conf")
        with open(path, "w") as f:
            f.write('LATITUDE="50.1"\nDATABASE_LANG="en"\nMixedCase="x"\n')
        conf = helpers.get_settings(path, force_reload=True)
        self.assertEqual(conf["LATITUDE"], "50.1")
        self.assertEqual(conf["DATABASE_LANG"], "en")
        self.assertEqual(conf["MixedCase"], "x")
        self.assertEqual(conf.getfloat("LATITUDE"), 50.1)


class TestModelLabels(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_strips_common_name_suffix(self):
        path = os.path.join(self.tmp.name, "M_Labels.txt")
        with open(path, "w") as f:
            f.write("Pica pica_Eurasian Magpie\nCorvus corax_Common Raven\n")
        with patch.object(helpers, "MODEL_PATH", self.tmp.name):
            self.assertEqual(helpers.get_model_labels("M"), ["Pica pica", "Corvus corax"])

    def test_keeps_labels_without_underscore(self):
        path = os.path.join(self.tmp.name, "M_Labels.txt")
        with open(path, "w") as f:
            f.write("Pica pica\nCorvus corax\n")
        with patch.object(helpers, "MODEL_PATH", self.tmp.name):
            self.assertEqual(helpers.get_model_labels("M"), ["Pica pica", "Corvus corax"])

    def test_real_labels_file_has_no_suffix(self):
        labels = helpers.get_model_labels("BirdNET_GLOBAL_6K_V2.4_Model_FP16")
        self.assertTrue(labels)
        self.assertNotIn("_", labels[0])


class TestLanguage(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.makedirs(os.path.join(self.tmp.name, "l18n"))

    def test_save_then_get_round_trips_sorted(self):
        labels = {"Corvus corax": "Common Raven", "Pica pica": "Eurasian Magpie"}
        with patch.object(helpers, "MODEL_PATH", self.tmp.name):
            helpers.save_language(labels, "en")
            on_disk = json.loads(open(os.path.join(self.tmp.name, "l18n", "labels_en.json")).read())
            self.assertEqual(list(on_disk.keys()), ["Corvus corax", "Pica pica"])
            self.assertEqual(helpers.get_language("en"), labels)


class TestGetFont(unittest.TestCase):
    def font_for(self, lang):
        with patch.object(helpers, "get_settings", return_value={"DATABASE_LANG": lang}):
            return helpers.get_font()

    def test_arabic(self):
        ret = self.font_for("ar")
        self.assertEqual(ret["font.family"], "Noto Sans Arabic")
        self.assertTrue(ret["path"].endswith("NotoSansArabic-Regular.ttf"))

    def test_cjk_share_jp_font(self):
        for lang in ("ja", "zh_CN", "zh_TW"):
            self.assertTrue(self.font_for(lang)["path"].endswith("NotoSansJP-Regular.ttf"))

    def test_korean(self):
        self.assertTrue(self.font_for("ko")["path"].endswith("NotoSansKR-Regular.ttf"))

    def test_default_roboto(self):
        self.assertEqual(self.font_for("en")["font.family"], "Roboto Flex")


class TestGetWavFiles(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.recs = self.tmp.name
        os.makedirs(os.path.join(self.recs, "2024-02-24", "Pica pica"))
        os.makedirs(os.path.join(self.recs, "StreamData"))
        self.dated = os.path.join(self.recs, "2024-02-24", "Pica pica", "a.wav")
        self.stream = os.path.join(self.recs, "StreamData", "b.wav")
        for p in (self.dated, self.stream):
            open(p, "w").close()

    def test_filters_open_files_and_sorts(self):
        with (
            patch.object(helpers, "get_settings", return_value={"RECS_DIR": self.recs}),
            patch.object(helpers, "get_open_files_in_dir", return_value=[self.stream]),
        ):
            files = helpers.get_wav_files()
        self.assertIn(self.dated, files)
        self.assertNotIn(self.stream, files)
        self.assertEqual(files, sorted(files))


if __name__ == "__main__":
    unittest.main()
