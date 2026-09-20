import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from utils import maintainer


def labels_for(mapping):
    return [f"{key}_{value}" for key, value in mapping.items()]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class TestGetLabels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.makedirs(os.path.join(self.tmp.name, "labels_l18n"))

    def write(self, name, text):
        with open(os.path.join(self.tmp.name, "labels_l18n", name), "w") as f:
            f.write(text)

    def test_without_language_reads_the_bare_file(self):
        self.write("labels.txt", "Pica pica_Eurasian Magpie\n")
        with patch.object(maintainer, "MODEL_PATH", self.tmp.name):
            self.assertEqual(maintainer.get_labels("l18n"), ["Pica pica_Eurasian Magpie"])

    def test_language_selects_the_suffixed_file_and_strips(self):
        self.write("labels_nl.txt", "  Pica pica_Ekster  \nCorvus corax_Raaf\n")
        with patch.object(maintainer, "MODEL_PATH", self.tmp.name):
            self.assertEqual(maintainer.get_labels("l18n", "nl"), ["Pica pica_Ekster", "Corvus corax_Raaf"])

    def test_missing_file_raises(self):
        with patch.object(maintainer, "MODEL_PATH", self.tmp.name):
            with self.assertRaises(FileNotFoundError):
                maintainer.get_labels("l18n", "xx")


class TestAsDict(unittest.TestCase):
    CASES = [
        ("default separator", ["Pica pica_Ekster"], {}, {"Pica pica": "Ekster"}),
        ("empty input", [], {}, {}),
        ("later duplicate wins", ["a_1", "a_2"], {}, {"a": "2"}),
        ("extra separators keep the first two fields", ["a_b_c"], {}, {"a": "b"}),
        ("custom separator", ["a|b"], {"den": "|"}, {"a": "b"}),
        ("reversed key and value", ["a_b"], {"key": 1, "value": 0}, {"b": "a"}),
    ]

    def test_table(self):
        for name, labels, kwargs, expected in self.CASES:
            with self.subTest(name):
                self.assertEqual(maintainer.as_dict(labels, **kwargs), expected)


class TestCreateLanguage(unittest.TestCase):
    EN = {
        "Pica pica": "Eurasian Magpie",
        "Corvus corax": "Common Raven",
        "Parus major": "Great Tit",
        "Turdus merula": "Common Blackbird",
    }
    L18N = {
        "Pica pica": "Ekster",
        "Corvus corax": "Raaf",
        "Parus major": "Koolmees",
        "Turdus merula": "Merel",
    }
    MODEL = {
        "Corvus corax": "Corvus corax",
        "Parus major": "Great Tit",
        "Turdus merula": "Zwarte merel",
    }

    def run_create(self):
        def get_labels(model, language=None):
            if model == "nm":
                return labels_for(self.MODEL)
            return labels_for(self.EN if language == "en" else self.L18N)

        save = MagicMock()
        with (
            patch.object(maintainer, "get_labels", side_effect=get_labels),
            patch.object(maintainer, "save_language", save),
            redirect_stdout(io.StringIO()),
        ):
            maintainer.create_language("nl")
        return save.call_args[0]

    def test_merge_rules(self):
        merged, language = self.run_create()
        self.assertEqual(language, "nl")
        self.assertEqual(merged["Pica pica"], "Ekster")
        self.assertEqual(merged["Corvus corax"], "Raaf")
        self.assertEqual(merged["Parus major"], "Koolmees")
        self.assertEqual(merged["Turdus merula"], "Zwarte merel")


class TestMeasureTranslations(unittest.TestCase):
    def measure(self, en, other):
        def get_language(language):
            return dict(en) if language == "en" else dict(other)

        with patch.object(maintainer, "get_language", side_effect=get_language):
            return maintainer.measure_translations("nl")

    def test_counts_only_the_rows_that_differ_from_english(self):
        en = {"a b": "Alpha", "c d": "Charlie", "e f": "Echo", "g h": "Golf"}
        other = {"a b": "Alfa", "c d": "Charlie", "e f": "Echo", "g h": "Golf"}
        self.assertEqual(self.measure(en, other), "| Dutch | 1 | 25.0% |")

    def test_all_translated(self):
        en = {"a b": "Alpha", "c d": "Charlie"}
        other = {"a b": "Alfa", "c d": "Karel"}
        self.assertEqual(self.measure(en, other), "| Dutch | 2 | 100.0% |")

    def test_none_translated(self):
        en = {"a b": "Alpha", "c d": "Charlie"}
        self.assertEqual(self.measure(en, dict(en)), "| Dutch | 0 | 0.0% |")


class TestMeasureAllLanguages(unittest.TestCase):
    def test_prints_a_header_and_every_language_but_english(self):
        with patch.object(maintainer, "measure_translations", side_effect=lambda lang: f"| {maintainer.key_lang[lang]} | 1 | 1.0% |"):
            out = io.StringIO()
            with redirect_stdout(out):
                maintainer.measure_all_languages()
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(lines[0], "| Language | Translated species | Translated species (%) |")
        rows = lines[2:]
        self.assertEqual(len(rows), len(maintainer.languages) - 1)
        self.assertNotIn("English", out.getvalue())
        self.assertEqual(rows, sorted(rows))


class TestLanguageTables(unittest.TestCase):
    def test_every_listed_language_has_a_display_name(self):
        self.assertEqual([lang for lang in maintainer.languages if lang not in maintainer.key_lang], [])

    def test_language_list_is_sorted_and_unique(self):
        self.assertEqual(maintainer.languages, sorted(set(maintainer.languages)))


class TestScrapeWikipedia(unittest.TestCase):
    def scrape(self, payload, failed=None):
        with patch.object(maintainer.requests, "get", return_value=FakeResponse(payload)), redirect_stdout(io.StringIO()):
            return maintainer.scrape_wikipedia("Pica pica", "nl", failed)

    def test_returns_the_title(self):
        self.assertEqual(self.scrape({"type": "standard", "title": "Ekster"}), "Ekster")

    def test_internal_error_is_ignored(self):
        failed = []
        self.assertIsNone(self.scrape({"type": "Internal error", "title": "Ekster"}, failed))
        self.assertEqual(failed, [])

    def test_disambiguation_is_recorded(self):
        failed = []
        self.assertIsNone(self.scrape({"type": "disambiguation", "title": "Ekster"}, failed))
        self.assertEqual(failed, [("nl", "Pica pica", "disambiguation")])

    def test_missing_title_returns_none(self):
        self.assertIsNone(self.scrape({"type": "standard"}))

    def test_title_equal_to_the_scientific_name_returns_none(self):
        with patch.object(maintainer.requests, "get", return_value=FakeResponse({"type": "standard", "title": "Pica pica"})):
            self.assertIsNone(maintainer.scrape_wikipedia("Pica pica", "nl"))

    def test_parenthetical_title_is_kept_verbatim(self):
        out = io.StringIO()
        with patch.object(maintainer.requests, "get", return_value=FakeResponse({"type": "standard", "title": "Ekster (vogel)"})), redirect_stdout(out):
            self.assertEqual(maintainer.scrape_wikipedia("Pica pica", "nl"), "Ekster (vogel)")
        self.assertIn("checkme", out.getvalue())

    def test_retries_once_before_giving_up(self):
        responses = [ConnectionError("boom"), FakeResponse({"type": "standard", "title": "Ekster"})]

        def get(**_kwargs):
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with patch.object(maintainer.requests, "get", side_effect=get), patch.object(maintainer.time, "sleep") as sleep:
            self.assertEqual(maintainer.scrape_wikipedia("Pica pica", "nl"), "Ekster")
        sleep.assert_called_once_with(1)
        self.assertEqual(responses, [])

    def test_two_failures_are_recorded(self):
        failed = []
        with patch.object(maintainer.requests, "get", side_effect=ConnectionError("boom")), patch.object(maintainer.time, "sleep"):
            self.assertIsNone(maintainer.scrape_wikipedia("Pica pica", "nl", failed))
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0][:2], ("nl", "Pica pica"))
        self.assertIn("boom", failed[0][2])


class TestAddTranslations(unittest.TestCase):
    EN = {"Pica pica": "Eurasian Magpie", "Corvus corax": "Common Raven", "Genus": "Genus"}
    NL = {"Pica pica": "Eurasian Magpie", "Corvus corax": "Raaf", "Genus": "Genus"}

    def run_add(self, scraped):
        def get_language(language):
            return dict(self.EN if language == "en" else self.NL)

        save = MagicMock()
        scrape = MagicMock(side_effect=lambda sci, lang, failed: scraped.get(sci))
        with (
            patch.object(maintainer, "get_language", side_effect=get_language),
            patch.object(maintainer, "save_language", save),
            patch.object(maintainer, "scrape_wikipedia", scrape),
            patch.object(maintainer.time, "sleep"),
            redirect_stdout(io.StringIO()),
        ):
            failed = maintainer.add_translations("nl")
        return save.call_args[0][0], scrape, failed

    def test_only_untranslated_binomials_are_scraped(self):
        _saved, scrape, _failed = self.run_add({})
        self.assertEqual([call.args[0] for call in scrape.call_args_list], ["Pica pica"])

    def test_a_hit_is_written_back(self):
        saved, _scrape, _failed = self.run_add({"Pica pica": "Ekster"})
        self.assertEqual(saved["Pica pica"], "Ekster")
        self.assertEqual(saved["Corvus corax"], "Raaf")

    def test_a_result_equal_to_english_is_not_written(self):
        saved, _scrape, _failed = self.run_add({"Pica pica": "Eurasian Magpie"})
        self.assertEqual(saved["Pica pica"], "Eurasian Magpie")

    def test_returns_the_failure_list(self):
        _saved, _scrape, failed = self.run_add({})
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
