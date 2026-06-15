import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest import mock

from utils import db

COLUMNS = "Date, Time, Sci_Name, Com_Name, Confidence, Lat, Lon, Cutoff, Week, Sens, Overlap, File_Name"


def row(date, time, sci, com, conf, fname):
    return (date, time, sci, com, conf, 50.0, 5.0, 0.7, 8, 1.25, 0.0, fname)


class DbTestCase(unittest.TestCase):
    def setUp(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute(f"CREATE TABLE detections ({COLUMNS})")
        self.con = con
        db._DB = con
        self.addCleanup(setattr, db, "_DB", None)
        self.addCleanup(con.close)

    def insert(self, *rows):
        self.con.executemany(f"INSERT INTO detections ({COLUMNS}) VALUES ({','.join(['?'] * 12)})", rows)
        self.con.commit()


class TestQueries(DbTestCase):
    def test_get_records_returns_rows(self):
        self.insert(row("2024-02-24", "10:00:00", "Pica pica", "Eurasian Magpie", 0.9, "a.wav"))
        records = db.get_records("SELECT * FROM detections")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Sci_Name"], "Pica pica")

    def test_get_records_swallows_sql_error(self):
        with mock.patch("utils.db.timeim.sleep"):
            self.assertEqual(db.get_records("SELECT * FROM nope"), [])

    def test_get_record_first_or_none(self):
        self.assertIsNone(db.get_record("SELECT * FROM detections"))
        self.insert(row("2024-02-24", "10:00:00", "Pica pica", "Eurasian Magpie", 0.9, "a.wav"))
        self.assertEqual(db.get_record("SELECT * FROM detections")["Com_Name"], "Eurasian Magpie")

    def test_get_latest_orders_by_date_then_time(self):
        self.insert(
            row("2024-02-24", "10:00:00", "Pica pica", "Eurasian Magpie", 0.9, "a.wav"),
            row("2024-02-25", "08:00:00", "Corvus corax", "Common Raven", 0.8, "b.wav"),
            row("2024-02-25", "09:30:00", "Turdus merula", "Blackbird", 0.7, "c.wav"),
        )
        self.assertEqual(db.get_latest()["Sci_Name"], "Turdus merula")

    def test_get_summary_counts(self):
        today = datetime.now().strftime("%Y-%m-%d")
        self.insert(
            row(today, "10:00:00", "Pica pica", "Eurasian Magpie", 0.9, "a.wav"),
            row(today, "11:00:00", "Pica pica", "Eurasian Magpie", 0.8, "b.wav"),
            row("2020-01-01", "11:00:00", "Corvus corax", "Common Raven", 0.8, "c.wav"),
        )
        summary = db.get_summary()
        self.assertEqual(summary["total_count"], 3)
        self.assertEqual(summary["todays_count"], 2)
        self.assertEqual(summary["todays_species_tally"], 1)
        self.assertEqual(summary["species_tally"], 2)

    def test_todays_and_weeks_count_for(self):
        today = datetime.now()
        within_week = (today - timedelta(days=3)).strftime("%Y-%m-%d")
        old = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        self.insert(
            row(today.strftime("%Y-%m-%d"), "10:00:00", "Pica pica", "Eurasian Magpie", 0.9, "a.wav"),
            row(within_week, "10:00:00", "Pica pica", "Eurasian Magpie", 0.9, "b.wav"),
            row(old, "10:00:00", "Pica pica", "Eurasian Magpie", 0.9, "c.wav"),
        )
        self.assertEqual(db.get_todays_count_for("Pica pica"), 1)
        self.assertEqual(db.get_this_weeks_count_for("Pica pica"), 2)
        self.assertEqual(db.get_todays_count_for("Absent species"), 0)

    def test_get_species_by_sorts(self):
        self.insert(
            row("2024-02-24", "10:00:00", "Pica pica", "Zebra Finch", 0.5, "a.wav"),
            row("2024-02-24", "11:00:00", "Pica pica", "Zebra Finch", 0.95, "b.wav"),
            row("2024-02-24", "12:00:00", "Corvus corax", "Common Raven", 0.6, "c.wav"),
        )
        by_occ = db.get_species_by("occurrences")
        self.assertEqual(by_occ[0]["Sci_Name"], "Pica pica")
        self.assertEqual(by_occ[0]["Count"], 2)
        by_conf = db.get_species_by("confidence")
        self.assertEqual(by_conf[0]["MaxConfidence"], 0.95)
        by_name = db.get_species_by()
        self.assertEqual(by_name[0]["Com_Name"], "Common Raven")


if __name__ == "__main__":
    unittest.main()
