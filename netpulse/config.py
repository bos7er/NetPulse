"""Application settings stored locally, never transmitted."""
from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict

from .network import validate_host

APP_VERSION = "1.0.0"
APP_NAME = "NetPulse"


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    location = (Path(base) if base else Path.home() / ".local" / "share") / APP_NAME
    location.mkdir(parents=True, exist_ok=True)
    return location


@dataclass
class Settings:
    target: str = "1.1.1.1"
    protocol: str = "ICMP"
    interval: int = 2
    interface: str = "Wszystkie"
    notifications: bool = True
    latency_alert: int = 150

    def validate(self) -> None:
        self.target = validate_host(self.target)
        if self.protocol not in ("ICMP", "TCP"):
            raise ValueError("Nieprawidłowy protokół.")
        if self.interval not in (2, 3, 5, 10):
            raise ValueError("Dozwolony interwał: 2, 3, 5, 10 sekund.")
        if not 20 <= self.latency_alert <= 1000:
            raise ValueError("Próg alertu musi wynosić 20–1000 ms.")
        if not isinstance(self.interface, str) or len(self.interface) > 128:
            raise ValueError("Nieprawidłowa nazwa interfejsu.")


def load_settings() -> Settings:
    path = data_dir() / "settings.json"
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            allowed = Settings.__dataclass_fields__.keys()
            result = Settings(**{key: value for key, value in stored.items() if key in allowed})
            result.validate()
            return result
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return Settings()


def save_settings(settings: Settings) -> None:
    settings.validate()
    dest = data_dir() / "settings.json"
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(dest)
