import os
import runpy
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from datetime import date, time
from unittest.mock import patch

import plotly.graph_objects as go

from tests.helpers import Settings

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plotly_streamlit.py")

ROWS = [
    ("2026-05-01", "06:00:00", "Pica pica", "Magpie", 0.70, "magpie-1.mp3"),
    ("2026-05-01", "06:05:00", "Pica pica", "Eurasian Magpie", 0.90, "magpie-2.mp3"),
    ("2026-05-02", "07:30:00", "Pica pica", "Eurasian Magpie", 0.80, "magpie-3.mp3"),
    ("2026-05-02", "18:00:00", "Turdus merula", "Common Blackbird", 0.75, "blackbird-1.mp3"),
    ("2026-05-03", "18:10:00", "Turdus merula", "Common Blackbird", 0.65, "blackbird-2.mp3"),
    ("2026-05-03", "12:00:00", "Parus major", "Great Tit", 0.60, "tit-1.mp3"),
]


class FakeStreamlit(types.ModuleType):
    def __init__(self, answers):
        super().__init__("streamlit")
        self.answers = answers
        self.charts = []
        self.infos = []
        self.subheaders = []
        self.images = []
        self.audios = []
        self.widgets = []
        self.sidebar = FakeSidebar(self)

    def _answer(self, kind, label, default, options=None):
        self.widgets.append((kind, label, options))
        for key, value in self.answers.items():
            if key[0] == kind and key[1] in label:
                return value
        return default

    def cache_resource(self, *args, **kwargs):
        return lambda fn: fn

    def cache_data(self, *args, **kwargs):
        return lambda fn: fn

    def set_page_config(self, **kwargs):
        pass

    def markdown(self, *args, **kwargs):
        pass

    def write(self, *args, **kwargs):
        pass

    def info(self, message):
        self.infos.append(message)

    def subheader(self, text):
        self.subheaders.append(text)

    def image(self, path):
        self.images.append(path)

    def audio(self, path):
        self.audios.append(path)

    def plotly_chart(self, fig, **kwargs):
        self.charts.append(fig)

    def columns(self, n):
        return [nullcontext() for _ in range(n)]

    def selectbox(self, label, options, index=0, **kwargs):
        options = list(options)
        return self._answer("selectbox", label, options[index] if options else None, options)


class FakeSidebar:
    def __init__(self, st):
        self.st = st

    def checkbox(self, label, **kwargs):
        return self.st._answer("checkbox", label, False)

    def date_input(self, label, value=None, **kwargs):
        return self.st._answer("date_input", label, value)

    def slider(self, label, value=None, **kwargs):
        return self.st._answer("slider", label, value)

    def radio(self, label, options, index=0, **kwargs):
        return self.st._answer("radio", label, options[index], list(options))

    def selectbox(self, label, options, index=0, **kwargs):
        return self.st.selectbox(label, options, index=index)


@contextmanager
def nullcontext():
    yield


@contextmanager
def swapped_module(name, module):
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def run_page(home, answers=None, settings=None):
    st = FakeStreamlit(answers or {})
    settings = settings or Settings.with_defaults()
    with (
        swapped_module("streamlit", st),
        patch.dict(os.environ, {"HOME": home}),
        patch("utils.helpers.get_settings", return_value=settings),
    ):
        namespace = runpy.run_path(SCRIPT)
    return st, namespace


def traces(fig, cls):
    return [t for t in fig.data if isinstance(t, cls)]


class PageTestCase(unittest.TestCase):
    rows = ROWS

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        db_dir = os.path.join(self.home, "BirdNET-Pi", "birdnet")
        os.makedirs(db_dir)
        con = sqlite3.connect(os.path.join(db_dir, "birds.db"))
        con.execute("CREATE TABLE detections (Date DATE, Time TIME, Sci_Name TEXT, Com_Name TEXT, Confidence FLOAT, File_Name TEXT)")
        con.executemany("INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?)", self.rows)
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def run_page(self, answers=None, settings=None):
        return run_page(self.home, answers, settings)


class TestEmptyDatabase(PageTestCase):
    rows = []

    def test_stops_with_a_friendly_message(self):
        with self.assertRaises(SystemExit) as ctx:
            self.run_page()
        self.assertEqual(ctx.exception.code, 0)


class TestAllSpeciesOverview(PageTestCase):
    def test_top_species_bar_polar_and_daily_totals_on_raw_data(self):
        st, _ = self.run_page({("radio", "Resample"): "Raw"})

        self.assertEqual(len(st.charts), 1)
        fig = st.charts[0]
        top, daily = traces(fig, go.Bar)
        self.assertEqual(top.y, ("Eurasian Magpie", "Common Blackbird", "Great Tit"))
        self.assertEqual(top.x, (3, 2, 1))
        self.assertEqual(daily.x, (date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)))
        self.assertEqual(daily.y, (2, 2, 2))

        (polar,) = traces(fig, go.Barpolar)
        self.assertEqual(len(polar.theta), 24)
        by_hour = dict(enumerate(polar.r[:24]))
        self.assertEqual({h: v for h, v in by_hour.items() if v}, {6: 2, 7: 1, 12: 1, 18: 2})

        titles = [a.text for a in fig.layout.annotations]
        self.assertIn("Total Detect:6", titles)
        self.assertIn("Top 3 Species in Date Range 2026-05-01 to 2026-05-03", titles[0])
        self.assertIn("Raw sampling interval", titles[0])

    def test_fifteen_minute_resample_counts_a_species_once_per_bin(self):
        st, _ = self.run_page()

        top, _ = traces(st.charts[0], go.Bar)
        self.assertEqual(dict(zip(top.y, top.x)), {"Eurasian Magpie": 2, "Common Blackbird": 2, "Great Tit": 1})
        self.assertIn("Total Detect:5", [a.text for a in st.charts[0].layout.annotations])

    def test_top_n_slider_limits_the_bar_chart(self):
        st, _ = self.run_page({("radio", "Resample"): "Raw", ("slider", "Number of Birds"): 2})

        top, _ = traces(st.charts[0], go.Bar)
        self.assertEqual(top.y, ("Eurasian Magpie", "Common Blackbird"))

    def test_species_picker_lists_all_then_species_by_count(self):
        st, _ = self.run_page({("radio", "Resample"): "Raw"})

        picker = next(w for w in st.widgets if w[0] == "selectbox" and "explore" in w[1])
        self.assertEqual(picker[2], ["All", "Eurasian Magpie", "Common Blackbird", "Great Tit"])

    def test_date_range_filters_detections(self):
        st, _ = self.run_page({("radio", "Resample"): "Raw", ("slider", "Date Range"): (date(2026, 5, 2), date(2026, 5, 2))})

        top, daily = traces(st.charts[0], go.Bar)
        self.assertEqual(dict(zip(top.y, top.x)), {"Eurasian Magpie": 1, "Common Blackbird": 1})
        self.assertEqual(daily.x, (date(2026, 5, 2),))


class TestSingleSpecies(PageTestCase):
    answers = {("radio", "Resample"): "Raw", ("selectbox", "explore"): "Eurasian Magpie"}

    def test_chart_and_confidence_summary(self):
        st, _ = self.run_page(self.answers)

        fig = st.charts[0]
        (polar,) = traces(fig, go.Barpolar)
        self.assertEqual({h: v for h, v in enumerate(polar.r[:24]) if v}, {6: 2, 7: 1})
        (daily,) = traces(fig, go.Bar)
        self.assertEqual(daily.y, (2, 1, 0))
        self.assertEqual(st.subheaders, ["Total Detect:3   Confidence Max:90.00%      Median:80.00%"])

    def test_recording_defaults_to_newest_under_latest_common_name(self):
        st, _ = self.run_page(self.answers)

        recordings = next(w for w in st.widgets if w[1] == "Recordings")
        self.assertEqual(recordings[2], ["magpie-3.mp3", "magpie-2.mp3", "magpie-1.mp3"])
        base = os.path.join(self.home, "BirdSongs", "Extracted", "By_Date", "2026-05-02", "Eurasian_Magpie", "magpie-3.mp3")
        self.assertEqual(st.audios, [base])
        self.assertEqual(st.images, [base + ".png"])

    def test_older_recording_resolves_to_the_directory_it_was_saved_under(self):
        st, _ = self.run_page({**self.answers, ("selectbox", "Recordings"): "magpie-1.mp3"})

        self.assertEqual(st.audios, [os.path.join(self.home, "BirdSongs", "Extracted", "By_Date", "2026-05-01", "Magpie", "magpie-1.mp3")])

    def test_missing_recording_shows_a_notice(self):
        st, _ = self.run_page({**self.answers, ("selectbox", "Recordings"): "gone.mp3"})

        self.assertEqual(st.infos, ["Recording not available"])
        self.assertEqual(st.audios, [])


class TestRecordingDirectoryName(PageTestCase):
    rows = [("2026-05-01", "06:00:00", "Calypte anna", "Anna's Hummingbird", 0.9, "anna-1.mp3")]

    def test_directory_strips_spaces_and_apostrophes(self):
        st, _ = self.run_page({("radio", "Resample"): "Raw", ("selectbox", "explore"): "Anna's Hummingbird"})

        self.assertEqual(st.audios, [os.path.join(self.home, "BirdSongs", "Extracted", "By_Date", "2026-05-01", "Annas_Hummingbird", "anna-1.mp3")])


class TestDailyHeatmap(PageTestCase):
    def test_heatmap_with_sunrise_and_sunset_line(self):
        settings = Settings.with_defaults()
        settings.update({"LATITUDE": 52.37, "LONGITUDE": 4.9})
        st, _ = self.run_page({("radio", "Resample"): "DAILY", ("selectbox", "explore"): "Eurasian Magpie"}, settings)

        picker = next(w for w in st.widgets if w[0] == "selectbox" and "explore" in w[1])
        self.assertEqual(set(picker[2][:2]), {"Eurasian Magpie", "Common Blackbird"})
        self.assertEqual(picker[2][2:], ["Great Tit"])

        fig = st.charts[0]
        (heat,) = traces(fig, go.Heatmap)
        (line,) = traces(fig, go.Scatter)
        self.assertEqual(heat.x, ("01-05-2026", "02-05-2026"))
        self.assertEqual(sum(map(sum, heat.z)), 3)
        self.assertEqual(len(heat.z), len(heat.y))
        self.assertTrue(all(0 <= y < 24 for y in heat.y))

        self.assertEqual(line.x, ("01-05-2026", "02-05-2026", None, "01-05-2026", "02-05-2026", None))
        self.assertIsNone(line.y[2])
        sunrise, sunset = line.y[:2], line.y[3:5]
        self.assertTrue(all(r < s for r, s in zip(sunrise, sunset)))
        self.assertTrue(line.text[0].endswith(" Sunrise"))
        self.assertTrue(line.text[3].endswith(" Sunset"))

    def test_colour_palette_comes_from_the_sidebar(self):
        st, _ = self.run_page({("radio", "Resample"): "DAILY", ("selectbox", "Color Pallet"): "viridis"})

        (heat,) = traces(st.charts[0], go.Heatmap)
        self.assertEqual(heat.colorscale[0][1], "#440154")


class TestSingleDayView(PageTestCase):
    answers = {("checkbox", "Single Day"): True, ("radio", "Resample"): "Raw"}

    def test_defaults_to_the_latest_day(self):
        st, _ = self.run_page(self.answers)

        fig = st.charts[0]
        (top,) = traces(fig, go.Bar)
        self.assertEqual(dict(zip(top.y, top.x)), {"Common Blackbird": 1, "Great Tit": 1})
        (heat,) = traces(fig, go.Heatmap)
        self.assertEqual(heat.x, tuple(range(24)))
        self.assertIn("<b>Top 2 Species For 2026-05-03</b>", [a.text for a in fig.layout.annotations])


class TestHelpers(PageTestCase):
    def setUp(self):
        super().setUp()
        _, self.ns = self.run_page({("radio", "Resample"): "Raw"})

    def test_hms_to_dec(self):
        for t, expected in [(time(0, 0), 0.0), (time(6, 30), 6.5), (time(23, 15, 36), 23.26)]:
            with self.subTest(t=t):
                self.assertAlmostEqual(self.ns["hms_to_dec"](t), expected)

    def test_hms_to_str(self):
        for t, expected in [(time(0, 0), "00:00"), (time(7, 5, 59), "07:05"), (time(23, 45), "23:45")]:
            with self.subTest(t=t):
                self.assertEqual(self.ns["hms_to_str"](t), expected)

    def test_normalise_com_name_uses_the_latest_name_and_keeps_the_original_as_directory(self):
        df = self.ns["df2"]
        magpies = df[df["Sci_Name"] == "Pica pica"]
        self.assertEqual(set(magpies["Com_Name"]), {"Eurasian Magpie"})
        self.assertEqual(list(magpies["Directory"]), ["Magpie", "Eurasian Magpie", "Eurasian Magpie"])
        self.assertEqual(str(df.index[0]), "2026-05-01 06:00:00")
