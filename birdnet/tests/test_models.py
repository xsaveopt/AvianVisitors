import io
import os
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import requests

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


LABELS = ["Pica pica", "Corvus corax", "Turdus merula"]


def logits_interpreter(logits):
    def factory(_model_path):
        interp = MagicMock()
        interp.get_input_details.return_value = [{"index": 0}, {"index": 1}]
        interp.get_output_details.return_value = [{"index": 10}, {"index": 11}, {"index": 12}, {"index": 13}]
        interp.get_tensor.return_value = np.array([logits])
        return interp

    return factory


class TestBirdNetV1(unittest.TestCase):
    def build(self, logits=(0.0, 2.0, -2.0), sens=1.0):
        with (
            patch("utils.models.tflite.Interpreter", side_effect=logits_interpreter(list(logits))),
            patch("utils.models.get_model_labels", return_value=LABELS),
        ):
            return models.BirdNetV1(sens)

    def test_metadata_uses_second_input(self):
        model = self.build()
        self.assertEqual(model._mdata_model, 1)
        self.assertEqual(model.chunk_duration, 3)
        self.assertEqual(model.sample_rate, 48000)

    def test_week_is_encoded_as_cosine(self):
        model = self.build()
        model.set_meta_data(50.0, 5.0, 8)
        np.testing.assert_allclose(model._mdata, [[50.0, 5.0, np.cos(np.radians(60)) + 1, 1.0, 1.0, 1.0]])

    def test_out_of_range_week_masks_week(self):
        model = self.build()
        model.set_meta_data(50.0, 5.0, 49)
        np.testing.assert_allclose(model._mdata, [[50.0, 5.0, -1.0, 1.0, 1.0, 0.0]])

    def test_unknown_location_masks_everything(self):
        model = self.build()
        model.set_meta_data(-1, -1, 8)
        np.testing.assert_allclose(model._mdata[0][3:], [0.0, 0.0, 0.0])

    def test_metadata_only_recomputed_on_change(self):
        model = self.build()
        model.set_meta_data(50.0, 5.0, 8)
        first = model._mdata
        model.set_meta_data(50.0, 5.0, 8)
        self.assertIs(model._mdata, first)
        model.set_meta_data(50.0, 5.0, 9)
        self.assertIsNot(model._mdata, first)

    def test_predict_feeds_audio_and_metadata(self):
        model = self.build()
        model.set_meta_data(50.0, 5.0, 8)
        result = model.predict([0.0] * 4)
        calls = model.interpreter.set_tensor.call_args_list
        self.assertEqual([c.args[0] for c in calls], [0, 1])
        self.assertEqual(calls[0].args[1].shape, (1, 4))
        self.assertEqual(calls[0].args[1].dtype, np.float32)
        self.assertEqual([label for label, _ in result], ["Corvus corax", "Pica pica", "Turdus merula"])
        self.assertAlmostEqual(float(result[1][1]), 0.5)

    def test_get_model_dispatches_v1(self):
        settings = Settings.with_defaults()
        with (
            patch("utils.models.get_settings", return_value=settings),
            patch("utils.models.tflite.Interpreter", side_effect=logits_interpreter([0.0])),
            patch("utils.models.get_model_labels", return_value=LABELS),
        ):
            self.assertIsInstance(models.get_model("BirdNET_6K_GLOBAL_MODEL"), models.BirdNetV1)


class ModelDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        patch("utils.models.MODEL_PATH", self.tmp.name).start()
        patch("utils.models.get_model_labels", return_value=LABELS).start()
        self.interp = patch("utils.models.tflite.Interpreter", side_effect=logits_interpreter([1.0, 3.0, 2.0])).start()


class TestPerch(ModelDirTestCase):
    def fake_download(self, url, path):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = b"tflite"
            info = tarfile.TarInfo("Perch_v2.tflite")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        with open(path, "wb") as f:
            f.write(buf.getvalue())

    def test_existing_model_is_not_downloaded(self):
        open(os.path.join(self.tmp.name, "Perch_v2.tflite"), "w").close()
        with patch("utils.models.download_file") as dl:
            models.Perch()
        dl.assert_not_called()

    def test_missing_model_is_downloaded_and_unpacked(self):
        with patch("utils.models.download_file", side_effect=self.fake_download) as dl:
            model = models.Perch()
        dl.assert_called_once_with(
            "https://github.com/Nachtzuster/BirdNET-Pi/releases/download/v0.11/Perch_v2.tar.gz",
            os.path.join(self.tmp.name, "Perch_v2.tar.gz"),
        )
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "Perch_v2.tflite")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "Perch_v2.tar.gz")))
        self.interp.assert_called_with(os.path.join(self.tmp.name, "Perch_v2.tflite"))
        self.assertEqual(model.chunk_duration, 5)
        self.assertEqual(model.sample_rate, 32000)

    def test_reads_fourth_output_and_applies_softmax(self):
        open(os.path.join(self.tmp.name, "Perch_v2.tflite"), "w").close()
        model = models.Perch()
        result = model.predict([0.0] * 4)
        model.interpreter.get_tensor.assert_called_with(13)
        self.assertEqual([label for label, _ in result], ["Corvus corax", "Turdus merula", "Pica pica"])
        self.assertAlmostEqual(sum(float(p) for _, p in result), 1.0, places=6)
        expected = np.exp([1.0, 3.0, 2.0]) / np.sum(np.exp([1.0, 3.0, 2.0]))
        self.assertAlmostEqual(float(result[0][1]), float(expected[1]), places=6)

    def test_get_model_dispatches_perch(self):
        open(os.path.join(self.tmp.name, "Perch_v2.tflite"), "w").close()
        with patch("utils.models.get_settings", return_value=Settings.with_defaults()):
            self.assertIsInstance(models.get_model("Perch_v2"), models.Perch)


class TestBirdNETGoEnsureModel(ModelDirTestCase):
    def test_downloads_labels_and_model_when_missing(self):
        with (
            patch("utils.models.download_file") as dl,
            patch("utils.models.get_meta_model", return_value=MagicMock()),
        ):
            models.BirdNETGo20250916(1.0)
        base = "https://raw.githubusercontent.com/tphakala/birdnet-go-classifiers/refs/heads/main/20250916"
        self.assertEqual(
            [c.args for c in dl.call_args_list],
            [
                (f"{base}/BirdNET-Go_classifier_20250916_Labels.txt", os.path.join(self.tmp.name, "BirdNET-Go_classifier_20250916_Labels.txt")),
                (f"{base}/BirdNET-Go_classifier_20250916.tflite", os.path.join(self.tmp.name, "BirdNET-Go_classifier_20250916.tflite")),
            ],
        )

    def test_present_model_skips_download(self):
        open(os.path.join(self.tmp.name, "BirdNET-Go_classifier_20250916.tflite"), "w").close()
        with (
            patch("utils.models.download_file") as dl,
            patch("utils.models.get_meta_model", return_value=MagicMock()),
        ):
            models.BirdNETGo20250916(1.0)
        dl.assert_not_called()


class TestDownloadFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = os.path.join(self.tmp.name, "model.tflite")

    def session(self, chunks=None, status_error=None, stream_error=None):
        response = MagicMock()
        if status_error:
            response.raise_for_status.side_effect = status_error

        def iter_content(_size):
            for c in chunks or []:
                yield c
            if stream_error:
                raise stream_error

        response.iter_content.side_effect = iter_content
        session = MagicMock()
        session.get.return_value = response
        return patch("utils.models.requests.Session", return_value=session), session

    def test_writes_streamed_chunks_to_target(self):
        p, session = self.session([b"abc", b"def"])
        with p:
            models.download_file("https://models.example/model.tflite", self.target)
        session.get.assert_called_once_with("https://models.example/model.tflite", stream=True)
        self.assertEqual(open(self.target, "rb").read(), b"abcdef")
        self.assertEqual(os.listdir(self.tmp.name), ["model.tflite"])

    def test_http_status_error_leaves_nothing(self):
        p, _ = self.session(status_error=requests.exceptions.HTTPError("404"))
        with p, self.assertRaises(requests.exceptions.HTTPError):
            models.download_file("https://models.example/model.tflite", self.target)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_http_error_mid_stream_removes_partial_file(self):
        p, _ = self.session([b"abc"], stream_error=requests.exceptions.HTTPError("reset"))
        with p, self.assertRaises(requests.exceptions.HTTPError):
            models.download_file("https://models.example/model.tflite", self.target)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_connection_drop_mid_stream_removes_partial_file(self):
        p, _ = self.session([b"abc"], stream_error=requests.exceptions.ConnectionError("reset"))
        with p, self.assertRaises(requests.exceptions.ConnectionError):
            models.download_file("https://models.example/model.tflite", self.target)
        self.assertEqual(os.listdir(self.tmp.name), [])


if __name__ == "__main__":
    unittest.main()
