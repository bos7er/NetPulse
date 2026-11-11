"""Safe, read-only network measurements. No packet capture or registry changes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import platform
import re
import socket
import subprocess
import time

import psutil


@dataclass(frozen=True)
class ProbeResult:
    timestamp: str
    ok: bool
    latency_ms: float | None
    protocol: str
    error: str = ""


_HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_TIME_RE = re.compile(r"(?:time|czas)\s*([=<])\s*(\d+(?:[,.]\d+)?)\s*ms", re.IGNORECASE)


def validate_host(host: str) -> str:
    """Accept IPv4, IPv6, or simple ASCII DNS names; never shell-expand input."""
    host = host.strip()
    if not host or len(host) > 253:
        raise ValueError("Podaj prawidłowy adres IP lub domenę.")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if not _HOST_RE.fullmatch(host) or ".." in host or host.startswith("-"):
        raise ValueError("Nieprawidłowa domena lub adres IP.")
    if any(not part or len(part) > 63 or part.startswith("-") or part.endswith("-") for part in host.split(".")):
        raise ValueError("Nieprawidłowa nazwa hosta.")
    return host


def parse_ping_latency(output: str) -> float | None:
    """Parses English and Polish Windows/Linux ping output (time=, czas=, <1ms)."""
    match = _TIME_RE.search(output)
    if match is None:
        return None
    value = float(match.group(2).replace(",", "."))
    return min(value, 0.5) if match.group(1) == "<" else value


def probe(host: str, protocol: str = "ICMP", timeout: float = 1.4) -> ProbeResult:
    host = validate_host(host)
    proto = protocol.upper()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if proto == "TCP":
        try:
            start = time.perf_counter()
            with socket.create_connection((host, 443), timeout=timeout):
                elapsed = (time.perf_counter() - start) * 1000
            return ProbeResult(now, True, round(elapsed, 1), "TCP")
        except (OSError, TimeoutError) as exc:
            return ProbeResult(now, False, None, "TCP", str(exc)[:150])
    if proto != "ICMP":
        raise ValueError("Tryb musi mieć wartość ICMP lub TCP.")
    system = platform.system()
    if system == "Windows":
        args = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    else:
        args = ["ping", "-n", "-c", "1", "-W", str(max(1, int(timeout + 0.999))), host]
    try:
        completed = subprocess.run(
            args, capture_output=True, text=True, errors="replace", encoding="utf-8",
            timeout=timeout + 1.5, check=False, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            return ProbeResult(now, False, None, "ICMP", "Brak odpowiedzi (ICMP).")
        latency = parse_ping_latency(completed.stdout + "\n" + completed.stderr)
        if latency is None:
            return ProbeResult(now, False, None, "ICMP", "Nie udało się odczytać odpowiedzi ping.")
        return ProbeResult(now, True, latency, "ICMP")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ProbeResult(now, False, None, "ICMP", str(exc)[:150])


def available_interfaces() -> list[str]:
    stats = psutil.net_if_stats()
    interfaces = [name for name, state in stats.items() if state.isup and not name.lower().startswith(("lo", "loopback"))]
    return sorted(interfaces, key=str.lower)


def get_counters(interface: str = "Wszystkie") -> tuple[int, int]:
    """Total received and sent bytes (never an internet speed test)."""
    if interface == "Wszystkie":
        count = psutil.net_io_counters()
    else:
        count = psutil.net_io_counters(pernic=True).get(interface)
    if count is None:
        raise ValueError("Nie znaleziono wskazanego interfejsu sieciowego.")
    return count.bytes_recv, count.bytes_sent


def calc_rates(previous: tuple[int, int], current: tuple[int, int], seconds: float) -> tuple[float, float]:
    if seconds <= 0:
        return 0.0, 0.0
    # A reset, unplugged NIC, or counter overflow must not show negative speed.
    return max(0, current[0] - previous[0]) / seconds, max(0, current[1] - previous[1]) / seconds


def format_rate(value: float) -> str:
    size = max(0.0, float(value))
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if size < 1024 or unit == "GB/s":
            return f"{size:.1f} {unit}" if unit != "B/s" else f"{size:.0f} {unit}"
        size /= 1024
    return "0 B/s"
