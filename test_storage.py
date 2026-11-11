import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from netpulse.storage import HistoryStore


class StorageTests(unittest.TestCase):
    def test_history_and_csv_export(self):
        with TemporaryDirectory() as tmp:
            db = HistoryStore(Path(tmp) / "history.sqlite3")
            db.add_sample("2026-11-11T10:00:00+00:00", "1.1.1.1", "ICMP", True, 12.5, 2048, 1024)
            db.add_sample("2026-11-11T10:00:02+00:00", "1.1.1.1", "ICMP", False, None, 0, 0)
            db.add_event("2026-11-11T10:00:02+00:00", "Brak odpowiedzi", "Test")
            self.assertEqual(db.counts(), (2, 1))
            self.assertEqual(db.recent_events(1)[0][1], "Brak odpowiedzi")
            self.assertEqual(db.recent_samples(1)[0][3], 0)
            out = Path(tmp) / "out.csv"
            self.assertEqual(db.export_csv(out), 2)
            with out.open(encoding="utf-8-sig", newline="") as file:
                self.assertEqual(len(list(csv.reader(file))), 3)

    def test_prune_old_records(self):
        with TemporaryDirectory() as tmp:
            store = HistoryStore(Path(tmp) / "store.db")
            store.add_sample("2020-01-01T00:00:00+00:00", "test", "ICMP", False, None, 0, 0)
            store.add_event("2020-01-01T00:00:00+00:00", "Test", "Old")
            store.prune(30)
            self.assertEqual(store.counts(), (0, 0))


if __name__ == "__main__":
    unittest.main()
