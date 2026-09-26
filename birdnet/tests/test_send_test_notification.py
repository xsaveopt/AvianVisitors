import logging
import os
import runpy
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

from tests.helpers import Settings
from utils import notifications

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "send_test_notification.py")

ARGV = [SCRIPT, "--config", "/data/apprise.txt", "--title", "Test title", "--body", "/data/body.txt"]


class TestSendTestNotification(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.with_defaults()
        root = logging.getLogger()
        self.handlers = list(root.handlers)
        self.level = root.level
        self.addCleanup(self.restore_logging)
        patcher = patch.multiple(notifications, APPRISE_CONFIG=notifications.APPRISE_CONFIG, APPRISE_BODY=notifications.APPRISE_BODY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def restore_logging(self):
        root = logging.getLogger()
        root.handlers[:] = self.handlers
        root.setLevel(self.level)

    def run_script(self, latest, argv=ARGV):
        with (
            patch.object(sys, "argv", argv),
            patch("utils.helpers.get_settings", return_value=self.settings),
            patch("utils.db.get_latest", return_value=latest),
            patch("utils.notifications.sendAppriseNotifications") as send,
        ):
            runpy.run_path(SCRIPT, run_name="__main__")
        return send

    def test_sends_the_latest_detection(self):
        latest = {
            "Sci_Name": "Pica pica",
            "Com_Name": "Eurasian Magpie",
            "Confidence": 0.876,
            "File_Name": "magpie.mp3",
            "Date": "2026-05-01",
            "Time": "06:00:00",
            "Week": 18,
            "Lat": 52.0,
            "Lon": 4.0,
            "Cutoff": 0.7,
            "Sens": 1.25,
            "Overlap": 0.0,
        }
        send = self.run_script(latest)

        send.assert_called_once_with("Pica pica", "Eurasian Magpie", 0.876, 88, "magpie.mp3", "2026-05-01", "06:00:00", 18, 52.0, 4.0, 0.7, 1.25, 0.0)

    def test_falls_back_to_a_placeholder_detection_from_settings(self):
        self.settings.update({"LATITUDE": 52.37, "LONGITUDE": 4.9, "CONFIDENCE": 0.8, "SENSITIVITY": 1.1, "OVERLAP": 0.5})
        before = datetime.now()
        send = self.run_script(None)
        after = datetime.now()

        args = send.call_args.args
        self.assertEqual(args[:5], ("Aptenodytes patagonicus", "King Penguin", 0.84, 84, "this_is_not_a_file.mp3"))
        self.assertIn(args[5], {before.strftime("%Y-%m-%d"), after.strftime("%Y-%m-%d")})
        self.assertRegex(args[6], r"^\d{2}:\d{2}:\d{2}$")
        self.assertIn(args[7], {before.isocalendar()[1], after.isocalendar()[1]})
        self.assertEqual(args[8:], (52.37, 4.9, 0.8, 1.1, 0.5))

    def test_forces_every_detection_mode_with_the_given_title_config_and_body(self):
        self.settings.update({"APPRISE_NOTIFY_NEW_SPECIES": "1", "APPRISE_NOTIFY_NEW_SPECIES_EACH_DAY": "1"})
        self.run_script(None)

        self.assertEqual(self.settings["APPRISE_NOTIFICATION_TITLE"], "Test title")
        self.assertEqual(self.settings["APPRISE_NOTIFY_EACH_DETECTION"], "1")
        self.assertEqual(self.settings["APPRISE_NOTIFY_NEW_SPECIES"], "0")
        self.assertEqual(self.settings["APPRISE_NOTIFY_NEW_SPECIES_EACH_DAY"], "0")
        self.assertEqual(notifications.APPRISE_CONFIG, "/data/apprise.txt")
        self.assertEqual(notifications.APPRISE_BODY, "/data/body.txt")

    def test_requires_all_arguments(self):
        for missing in ("--config", "--title", "--body"):
            with self.subTest(missing=missing):
                i = ARGV.index(missing)
                argv = ARGV[:i] + ARGV[i + 2 :]
                with self.assertRaises(SystemExit) as ctx:
                    self.run_script(None, argv)
                self.assertEqual(ctx.exception.code, 2)
