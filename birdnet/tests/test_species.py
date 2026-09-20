import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import species
from tests.helpers import Settings


class FakeModels(types.ModuleType):
    def __init__(self):
        super().__init__("utils.models")
        self.MDataModel1 = MagicMock(name="MDataModel1")
        self.MDataModel2 = MagicMock(name="MDataModel2")


class TestReadLabels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, text):
        path = os.path.join(self.tmp.name, "labels.txt")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_strips_each_line(self):
        path = self.write("  Pica pica_Eurasian Magpie \nCorvus corax_Common Raven\n")
        self.assertEqual(species.read_labels(path), ["Pica pica_Eurasian Magpie", "Corvus corax_Common Raven"])

    def test_keeps_blank_lines_as_empty_strings(self):
        path = self.write("a\n\nb\n")
        self.assertEqual(species.read_labels(path), ["a", "", "b"])

    def test_empty_file(self):
        self.assertEqual(species.read_labels(self.write("")), [])

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            species.read_labels(os.path.join(self.tmp.name, "nope.txt"))


class TestBuildModel(unittest.TestCase):
    def build(self, version, threshold=0.05):
        conf = Settings.with_defaults()
        conf["DATA_MODEL_VERSION"] = version
        models = FakeModels()
        with patch.dict(sys.modules, {"utils.models": models}):
            return species.build_model(conf, threshold), models

    def test_version_one_uses_the_first_meta_model(self):
        model, models = self.build(1)
        models.MDataModel1.assert_called_once_with(0.05)
        models.MDataModel2.assert_not_called()
        self.assertIs(model, models.MDataModel1.return_value)

    def test_any_other_version_uses_the_second_meta_model(self):
        for version in (2, 3):
            with self.subTest(version=version):
                model, models = self.build(version)
                models.MDataModel2.assert_called_once_with(0.05)
                models.MDataModel1.assert_not_called()
                self.assertIs(model, models.MDataModel2.return_value)

    def test_threshold_is_passed_through(self):
        _model, models = self.build(1, threshold=0.5)
        models.MDataModel1.assert_called_once_with(0.5)

    def test_version_is_read_as_an_integer(self):
        conf = Settings.with_defaults()
        conf["DATA_MODEL_VERSION"] = "1"
        models = FakeModels()
        with patch.dict(sys.modules, {"utils.models": models}):
            species.build_model(conf, 0.05)
        models.MDataModel1.assert_called_once_with(0.05)


class TestFormatSpecies(unittest.TestCase):
    CASES = [
        ((0.1234567, "Pica pica"), "Pica pica - 0.1235"),
        ((1.0, "Parus major"), "Parus major - 1.0000"),
        ((0.0, "Corvus corax"), "Corvus corax - 0.0000"),
        ((0.00004, "Turdus merula"), "Turdus merula - 0.0000"),
    ]

    def test_table(self):
        for entry, expected in self.CASES:
            with self.subTest(entry[1]):
                self.assertEqual(species.format_species(entry), expected)


if __name__ == "__main__":
    unittest.main()
