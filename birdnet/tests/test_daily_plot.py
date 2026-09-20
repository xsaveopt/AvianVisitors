import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("MPLBACKEND", "Agg")

import pandas as pd
from matplotlib import rcParams

import daily_plot

COLUMNS = "Date, Time, Sci_Name, Com_Name, Confidence"


class Stop(Exception):
    pass


class FakePatch:
    def __init__(self, x, y, width, height):
        self.x, self.y, self.width, self.height = x, y, width, height

    def get_x(self):
        return self.x

    def get_y(self):
        return self.y

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height


class FakeAxes:
    def __init__(self, patches):
        self.patches = patches
        self.texts = []

    def text(self, x, y, value, **kwargs):
        self.texts.append((x, y, value, kwargs))


class TestWrapWidth(unittest.TestCase):
    CASES = [
        ("", 16),
        ("aaa", 16),
        ("MMM", 15),
        ("iii", 17),
        ("Mi", 16),
        ("WWWWWW", 14),
        ("llllll", 18),
    ]

    def test_table(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(daily_plot.wrap_width(text), expected)

    def test_result_is_always_an_integer(self):
        for text, _expected in self.CASES:
            self.assertIsInstance(daily_plot.wrap_width(text), int)


class TestGetData(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "birds.db")
        con = sqlite3.connect(self.db)
        con.execute(f"CREATE TABLE detections ({COLUMNS})")
        con.executemany(
            f"INSERT INTO detections ({COLUMNS}) VALUES (?,?,?,?,?)",
            [
                ("2024-02-24", "06:15:00", "Pica pica", "Eurasian Magpie", 0.9),
                ("2024-02-24", "23:45:00", "Corvus corax", "Common Raven", 0.8),
                ("2024-02-23", "12:00:00", "Parus major", "Great Tit", 0.7),
            ],
        )
        con.commit()
        con.close()

    def fetch(self, now):
        with patch.object(daily_plot, "DB_PATH", self.db):
            return daily_plot.get_data(now)

    def test_selects_only_the_requested_day(self):
        df, _now = self.fetch(datetime(2024, 2, 24, 8, 0))
        self.assertEqual(sorted(df["Sci_Name"]), ["Corvus corax", "Pica pica"])

    def test_adds_the_hour_of_day_column(self):
        df, _now = self.fetch(datetime(2024, 2, 24, 8, 0))
        self.assertEqual(sorted(df["Hour of Day"]), [6, 23])

    def test_parses_the_date_column(self):
        df, _now = self.fetch(datetime(2024, 2, 24, 8, 0))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["Date"]))

    def test_returns_the_timestamp_it_was_given(self):
        now = datetime(2024, 2, 24, 8, 0)
        _df, returned = self.fetch(now)
        self.assertIs(returned, now)

    def test_defaults_to_the_current_time(self):
        with patch.object(daily_plot, "DB_PATH", self.db):
            _df, returned = daily_plot.get_data()
        self.assertIsInstance(returned, datetime)

    def test_a_day_without_detections_is_empty(self):
        df, _now = self.fetch(datetime(2024, 2, 20, 8, 0))
        self.assertTrue(df.empty)


class TestShowValuesOnBars(unittest.TestCase):
    def render(self, scheme, patches):
        ax = FakeAxes(patches)
        with patch.object(daily_plot, "get_settings", return_value={"COLOR_SCHEME": scheme}):
            daily_plot.show_values_on_bars(ax, None)
        return ax

    def test_labels_every_bar_with_its_width(self):
        ax = self.render("light", [FakePatch(0, 0, 3.0, 0.8), FakePatch(0, 1, 12.0, 0.8)])
        self.assertEqual([text[2] for text in ax.texts], ["3", "12"])

    def test_places_the_label_near_the_end_of_the_bar(self):
        ax = self.render("light", [FakePatch(1.0, 2.0, 10.0, 0.8)])
        x, y, _value, _kwargs = ax.texts[0]
        self.assertAlmostEqual(x, 10.0)
        self.assertAlmostEqual(y, 2.4)

    def test_colour_follows_the_scheme(self):
        for scheme, expected in (("dark", "black"), ("light", "darkgreen")):
            with self.subTest(scheme=scheme):
                ax = self.render(scheme, [FakePatch(0, 0, 1.0, 0.8)])
                self.assertEqual(ax.texts[0][3]["color"], expected)

    def test_no_bars_means_no_labels(self):
        self.assertEqual(self.render("light", []).texts, [])


class TestLoadFonts(unittest.TestCase):
    def setUp(self):
        self.addCleanup(rcParams.__setitem__, "font.family", rcParams["font.family"])

    def test_registers_the_bundled_fonts_and_selects_the_family(self):
        manager = MagicMock()
        manager.findSystemFonts.return_value = ["/fonts/RobotoFlex-Regular.ttf"]
        with (
            patch.object(daily_plot, "font_manager", manager),
            patch.object(daily_plot, "get_font", return_value={"font.family": "Noto Sans JP"}),
        ):
            daily_plot.load_fonts()
        manager.findSystemFonts.assert_called_once_with([daily_plot.FONT_DIR], fontext="ttf")
        manager.fontManager.addfont.assert_called_once_with("/fonts/RobotoFlex-Regular.ttf")
        self.assertEqual(rcParams["font.family"], ["Noto Sans JP"])


class TestMain(unittest.TestCase):
    def setUp(self):
        self.create_plot = MagicMock()
        self.frame = pd.DataFrame({"Sci_Name": ["Pica pica"]})

    def run_main(self, daemon, get_data, now_values=(), sleeps=()):
        clock = MagicMock()
        clock.now.side_effect = list(now_values) or [datetime(2024, 2, 24, 8, 0)]
        sleep = MagicMock(side_effect=list(sleeps) or [None])
        with (
            patch.object(daily_plot, "load_fonts"),
            patch.object(daily_plot, "get_data", get_data),
            patch.object(daily_plot, "create_plot", self.create_plot),
            patch.object(daily_plot, "datetime", clock),
            patch.object(daily_plot, "sleep", sleep),
        ):
            if daemon:
                with self.assertRaises(Stop):
                    daily_plot.main(True, 2)
            else:
                daily_plot.main(False, 2)
        return sleep

    def test_single_run_plots_once_and_does_not_sleep(self):
        now = datetime(2024, 2, 24, 8, 0)
        sleep = self.run_main(False, MagicMock(return_value=(self.frame, now)), now_values=[now])
        self.create_plot.assert_called_once_with(self.frame, now)
        sleep.assert_not_called()

    def test_an_empty_dataset_is_not_plotted(self):
        now = datetime(2024, 2, 24, 8, 0)
        self.run_main(False, MagicMock(return_value=(pd.DataFrame(), now)), now_values=[now])
        self.create_plot.assert_not_called()

    def test_daemon_sleeps_for_the_requested_minutes(self):
        now = datetime(2024, 2, 24, 8, 0)
        get_data = MagicMock(return_value=(self.frame, now))
        sleep = self.run_main(True, get_data, now_values=[now, now], sleeps=[None, Stop()])
        self.assertEqual(sleep.call_args_list[0].args, (120,))

    def test_a_new_day_replots_yesterday_at_its_last_minute(self):
        first = datetime(2024, 2, 24, 23, 50)
        second = datetime(2024, 2, 25, 0, 10)
        get_data = MagicMock(side_effect=[(self.frame, first), (self.frame, second)])
        self.run_main(True, get_data, now_values=[first, second], sleeps=[None, Stop()])
        self.assertEqual(get_data.call_args_list[0].args, (first,))
        self.assertEqual(get_data.call_args_list[1].args, (datetime(2024, 2, 24, 23, 59),))

    def test_same_day_reruns_use_the_current_time(self):
        first = datetime(2024, 2, 24, 8, 0)
        second = datetime(2024, 2, 24, 8, 2)
        get_data = MagicMock(side_effect=[(self.frame, first), (self.frame, second)])
        self.run_main(True, get_data, now_values=[first, second], sleeps=[None, Stop()])
        self.assertEqual(get_data.call_args_list[1].args, (second,))


if __name__ == "__main__":
    unittest.main()
