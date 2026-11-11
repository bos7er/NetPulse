"""Local SQLite history and CSV export."""
from __future__ import annotations

import csv
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from .config import data_dir


def default_db_path() -> Path:
    return data_dir() / "history.sqlite3"


class HistoryStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                target TEXT NOT NULL,
                protocol TEXT NOT NULL,
                ok INTEGER NOT NULL,
                latency_ms REAL,
                rx_bps REAL NOT NULL,
                tx_bps REAL NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS ix_samples_time ON samples(recorded_at)")
            db.execute("CREATE INDEX IF NOT EXISTS ix_events_time ON events(recorded_at)")

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=8)
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_sample(self, when: str, target: str, protocol: str, ok: bool,
                   latency_ms: float | None, rx_bps: float, tx_bps: float) -> None:
        with self._connection() as db:
            db.execute("""INSERT INTO samples
                (recorded_at,target,protocol,ok,latency_ms,rx_bps,tx_bps)
                VALUES (?,?,?,?,?,?,?)""",
                (when, target, protocol, int(ok), latency_ms, rx_bps, tx_bps))

    def add_event(self, when: str, category: str, message: str) -> None:
        with self._connection() as db:
            db.execute("INSERT INTO events(recorded_at, category, message) VALUES(?,?,?)", (when, category, message))

    def recent_events(self, limit: int = 50):
        with self._connection() as db:
            return db.execute("""SELECT recorded_at,category,message FROM events
                ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()

    def recent_samples(self, limit: int = 100):
        with self._connection() as db:
            return db.execute("""SELECT recorded_at,target,protocol,ok,latency_ms,rx_bps,tx_bps
                FROM samples ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()

    def counts(self) -> tuple[int, int]:
        with self._connection() as db:
            n1 = db.execute("SELECT count(*) FROM samples").fetchone()[0]
            n2 = db.execute("SELECT count(*) FROM events").fetchone()[0]
            return n1, n2

    def prune(self, days: int = 30) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self._connection() as db:
            db.execute("DELETE FROM samples WHERE recorded_at < ?", (cutoff,))
            db.execute("DELETE FROM events WHERE recorded_at < ?", (cutoff,))

    def export_csv(self, path: Path) -> int:
        """Stream samples to disk without loading the entire history into memory."""
        count = 0
        with self._connection() as db, path.open("w", encoding="utf-8-sig", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["czas_utc", "cel", "protokol", "odpowiedz", "latencja_ms", "pobieranie_B_s", "wysylanie_B_s"])
            cursor = db.execute("""SELECT recorded_at,target,protocol,ok,latency_ms,rx_bps,tx_bps
                FROM samples ORDER BY id ASC""")
            for row in cursor:
                writer.writerow(row)
                count += 1
        return count
