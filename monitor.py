"""Background sampling. The Tkinter UI is never accessed from this thread."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from queue import Queue
import statistics
import threading
import time

from .config import Settings
from .network import ProbeResult, calc_rates, get_counters, probe
from .storage import HistoryStore


@dataclass(frozen=True)
class Sample:
    probe: ProbeResult
    download_bps: float
    upload_bps: float
    loss_pct: float
    jitter_ms: float | None
    total: int
    failed: int


class Monitor:
    def __init__(self, settings: Settings, store: HistoryStore, events: Queue):
        self.settings = Settings(**vars(settings))
        self.store = store
        self.events = events
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._results: deque[float | None] = deque(maxlen=60)
        self._failed = 0
        self._total = 0
        self._previous_ok = True
        self._latency_strikes = 0
        self._latency_warning_sent = False
        self._last_storage_warning = 0.0

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="NetPulse-Monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.5)

    def _emit_event(self, category: str, message: str, notify: bool = False) -> None:
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            self.store.add_event(ts, category, message)
        except OSError as exc:
            self.events.put(("storage_error", str(exc)))
        self.events.put(("event", (ts, category, message, notify)))

    def _run(self) -> None:
        last_bytes = None
        last_tick = time.perf_counter()
        self.events.put(("state", "running"))
        while not self._stop.is_set():
            started = time.perf_counter()
            try:
                outcome = probe(self.settings.target, self.settings.protocol, timeout=1.4)
                now_tick = time.perf_counter()
                try:
                    current_bytes = get_counters(self.settings.interface)
                    rates = calc_rates(last_bytes, current_bytes, now_tick - last_tick) if last_bytes else (0.0, 0.0)
                    last_bytes = current_bytes
                    last_tick = now_tick
                except (OSError, ValueError) as exc:
                    rates = (0.0, 0.0)
                    last_bytes = None
                    self.events.put(("interface_error", str(exc)))

                self._total += 1
                if not outcome.ok:
                    self._failed += 1
                self._results.append(outcome.latency_ms if outcome.ok else None)
                successful = [x for x in self._results if x is not None]
                jitter = (statistics.mean(abs(b - a) for a, b in zip(successful, successful[1:]))
                          if len(successful) > 1 else None)
                loss = 100 * sum(x is None for x in self._results) / len(self._results)
                sample = Sample(outcome, rates[0], rates[1], loss, jitter, self._total, self._failed)
                self.events.put(("sample", sample))
                try:
                    self.store.add_sample(outcome.timestamp, self.settings.target,
                                          outcome.protocol, outcome.ok, outcome.latency_ms, *rates)
                except (OSError, ValueError) as exc:
                    if time.monotonic() - self._last_storage_warning > 60:
                        self._last_storage_warning = time.monotonic()
                        self.events.put(("storage_error", str(exc)))

                if not outcome.ok and self._previous_ok:
                    self._emit_event("Brak odpowiedzi", f"Brak odpowiedzi od {self.settings.target}.", True)
                elif outcome.ok and not self._previous_ok:
                    self._emit_event("Połączenie wróciło", f"Cel {self.settings.target} znów odpowiada.", True)
                self._previous_ok = outcome.ok

                if outcome.ok and outcome.latency_ms is not None and outcome.latency_ms >= self.settings.latency_alert:
                    self._latency_strikes += 1
                    if self._latency_strikes >= 3 and not self._latency_warning_sent:
                        self._emit_event("Wysokie opóźnienie",
                                         f"Co najmniej 3 pomiary powyżej {self.settings.latency_alert} ms.", True)
                        self._latency_warning_sent = True
                else:
                    self._latency_strikes = 0
                    self._latency_warning_sent = False
            except Exception as exc:  # prevent a recoverable probe failure from killing monitoring
                self.events.put(("error", f"Błąd pomiaru: {exc}"))
            elapsed = time.perf_counter() - started
            self._stop.wait(max(0.0, self.settings.interval - elapsed))
        self.events.put(("state", "stopped"))
