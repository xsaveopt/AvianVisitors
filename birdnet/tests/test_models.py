import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from tests.helpers import Settings
from utils import models


def fake_interpreter(species_filter):
    def factory(_model_path):
        interp = MagicMock()
        interp.get_input_details.return_value = [{"index": 0}, {"index": 1}]
        interp.get_output_details.return_value = [{"index": 10}, {"index": 11}, {"index": 12}, {"index": 13}]
        interp.get_tensor.return_value = np.array([species_filter])
        return interp

    return factory


class TestMDataModel(unittest.TestCase):
    LABELS = ["Pica pica_Eurasian Magpie", "Corvus corax_Common Raven", "Turdus merula_Blackbird"]

    def build(self, species_filter, sf_thresh=0.003):
        with patch("utils.models.tflite.Interpreter", side_effect=fake_interpreter(species_filter)):
            return models.MDataModel1(sf_thresh)

    def test_thresholds_and_sorts_species(self):
        model = self.build([0.5, 0.001, 0.3])
        model.set_meta_data(50.0, 5.0, 8)
        details = model.get_species_list_details(self.LABELS)
        self.assertEqual([label for _, label in details], ["Pica pica_Eurasian Magpie", "Turdus merula_Blackbird"])

    def test_get_species_list_strips_common_name(self):
        model = self.build([0.5, 0.001, 0.3])
        model.set_meta_data(50.0, 5.0, 8)
        self.assertEqual(model.get_species_list(self.LABELS), ["Pica pica", "Turdus merula"])

    def test_caches_until_meta_changes(self):
        model = self.build([0.5, 0.001, 0.3])
        model.set_meta_data(50.0, 5.0, 8)
        model.get_species_list(self.LABELS)
        model.get_species_list(self.LABELS)
        self.assertEqual(model.interpreter.invoke.call_count, 1)
        model.set_meta_data(10.0, 10.0, 1)
        model.get_species_list(self.LABELS)
        self.assertEqual(model.interpreter.invoke.call_count, 2)


class TestGetModelDispatch(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.with_defaults()
        self.p_interp = patch("utils.models.tflite.Interpreter", side_effect=fake_interpreter([0.5, 0.001, 0.3]))
        self.p_settings = patch("utils.models.get_settings", return_value=self.settings)
        self.p_interp.start()
        self.p_settings.start()
        self.addCleanup(self.p_interp.stop)
        self.addCleanup(self.p_settings.stop)

    def test_unknown_model_returns_none(self):
        self.assertIsNone(models.get_model("does-not-exist"))

    def test_returns_birdnet_v2_4(self):
        model = models.get_model("BirdNET_GLOBAL_6K_V2.4_Model_FP16")
        self.assertIsInstance(model, models.BirdNetV2_4)

    def test_sensitivity_clamped(self):
        self.settings["SENSITIVITY"] = 2.0
        self.assertEqual(models.get_model("BirdNET_GLOBAL_6K_V2.4_Model_FP16")._sensitivity, 0.5)
        self.settings["SENSITIVITY"] = 0.0
        self.assertEqual(models.get_model("BirdNET_GLOBAL_6K_V2.4_Model_FP16")._sensitivity, 1.5)

    def test_scale_is_sigmoid(self):
        model = models.get_model("BirdNET_GLOBAL_6K_V2.4_Model_FP16")
        self.assertAlmostEqual(float(model.scale(np.array([0.0]))[0]), 0.5)

    def test_get_meta_model_none_for_other_models(self):
        self.assertIsNone(models.get_meta_model("BirdNET_6K_GLOBAL_MODEL"))

    def test_get_meta_model_returns_mdata1(self):
        self.assertIsInstance(models.get_meta_model("BirdNET_GLOBAL_6K_V2.4_Model_FP16", version=1), models.MDataModel1)


if __name__ == "__main__":
    unittest.main()
