from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from unittest.mock import patch
import time
import unittest

from netpulse.config import Settings
from netpulse.monitor import Monitor
from netpulse.network import ProbeResult
from netpulse.storage import HistoryStore


class MonitorTests(unittest.TestCase):
    def test_monitor_starts_and_stops(self):
        with TemporaryDirectory() as temp:
            db = HistoryStore(Path(temp) / "db.sqlite")
            events = Queue()
            settings = Settings(interval=2)
            with patch("netpulse.monitor.probe") as test_probe, patch("netpulse.monitor.get_counters", return_value=(100, 200)):
                test_probe.return_value = ProbeResult(datetime.now(timezone.utc).isoformat(), True, 15, "ICMP")
                monitor = Monitor(settings, db, events)
                monitor.start()
                time.sleep(0.12)
                monitor.stop()
                self.assertFalse(monitor.running)
                self.assertGreaterEqual(db.counts()[0], 1)
                types = []
                while not events.empty():
                    types.append(events.get_nowait()[0])
                self.assertIn("sample", types)


if __name__ == "__main__":
    unittest.main()
