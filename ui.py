"""NetPulse GUI. Uses a background monitor and marshals all updates onto Tk's thread."""
from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .config import APP_VERSION, Settings, data_dir, load_settings, save_settings
from .monitor import Monitor, Sample
from .network import available_interfaces, format_rate
from .storage import HistoryStore

BG = "#0B1020"
PANEL = "#151E33"
PANEL_2 = "#1B2840"
BORDER = "#29374E"
TEXT = "#F4F7FC"
MUTED = "#91A1B8"
ACCENT = "#47E5BE"
BLUE = "#6B9AFF"
RED = "#FF6C7A"
YELLOW = "#FFBF69"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def text(parent, value: str, size: int = 14, weight: str = "normal", color: str = TEXT, **kwargs):
    return ctk.CTkLabel(parent, text=value, font=ctk.CTkFont(family="Segoe UI", size=size, weight=weight),
                        text_color=color, **kwargs)


def card(parent, **kwargs):
    return ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=17, border_width=1, border_color=BORDER, **kwargs)


def local_time(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.astimezone().strftime("%d.%m %H:%M:%S")
    except (ValueError, TypeError):
        return timestamp[:19]


class LatencyChart(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, background=PANEL, highlightthickness=0, bd=0, **kwargs)
        self.samples: deque[float | None] = deque(maxlen=90)
        self.bind("<Configure>", lambda _event: self.draw())

    def add(self, value: float | None):
        self.samples.append(value)
        self.draw()

    def reset(self):
        self.samples.clear()
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 120 or h < 80:
            return
        left, right, top, bottom = 42, w - 18, 18, h - 31
        values = list(self.samples)
        valid = [v for v in values if v is not None]
        max_v = max(100.0, max(valid, default=0) * 1.28)
        for row in range(5):
            y = top + (bottom - top) * row / 4
            self.create_line(left, y, right, y, fill=BORDER, dash=(3, 5))
            label = f"{int(max_v * (4 - row) / 4)}"
            self.create_text(left - 7, y, text=label, fill=MUTED, anchor="e", font=("Segoe UI", 9))
        self.create_text(left, h - 11, text="Najstarsze", fill=MUTED, anchor="w", font=("Segoe UI", 9))
        self.create_text(right, h - 11, text="Teraz", fill=MUTED, anchor="e", font=("Segoe UI", 9))
        if not values:
            self.create_text(w / 2, h / 2, text="Oczekiwanie na pierwszy pomiar...",
                             fill=MUTED, font=("Segoe UI", 12))
            return
        count = max(90, len(values))
        last_xy = None
        for i, value in enumerate(values):
            x = right - (len(values) - 1 - i) * (right - left) / (count - 1)
            if value is None:
                self.create_line(x, top, x, bottom, fill="#703B4C", dash=(3, 5))
                self.create_oval(x - 3.5, bottom - 3.5, x + 3.5, bottom + 3.5,
                                 fill=RED, outline="")
                last_xy = None
                continue
            y = bottom - min(value, max_v) / max_v * (bottom - top)
            if last_xy is not None:
                self.create_line(last_xy[0], last_xy[1], x, y, fill=ACCENT, width=2.7, smooth=True)
            last_xy = (x, y)
        if valid and last_xy:
            x, y = last_xy
            self.create_oval(x - 4, y - 4, x + 4, y + 4, fill=ACCENT, outline=PANEL, width=1)


class NetPulseApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"NetPulse {APP_VERSION} — Monitor sieci")
        self.geometry("1180x785")
        self.minsize(990, 695)
        self.configure(fg_color=BG)
        self.settings = load_settings()
        self.store = HistoryStore()
        try:
            self.store.prune()
        except OSError:
            pass
        self.event_queue: Queue = Queue()
        self.monitor: Monitor | None = None
        self.active_page = "Dashboard"
        self.session_count = 0
        self.session_failures = 0
        self.last_sample: Sample | None = None
        self.last_error = ""
        self._build_shell()
        self.show_page("Dashboard")
        self._start_monitor()
        self.after(250, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(self, width=208, fg_color="#10192C", corner_radius=0,
                               border_color=BORDER, border_width=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        titlebar = ctk.CTkFrame(sidebar, fg_color="transparent")
        titlebar.pack(fill="x", padx=20, pady=(31, 35))
        text(titlebar, "◉", 28, "bold", ACCENT).pack(side="left")
        text(titlebar, "NetPulse", 24, "bold").pack(side="left", padx=(10, 0))
        text(sidebar, "MONITOR SIECI", 10, "bold", MUTED, anchor="w").pack(fill="x", padx=25, pady=(0, 12))
        self.nav_buttons = {}
        for label, symbol in [("Dashboard", "▦"), ("Historia", "◷"),
                              ("Ustawienia", "⚙"), ("O aplikacji", "ⓘ")]:
            btn = ctk.CTkButton(
                sidebar, text=f"{symbol}    {label}", height=47, corner_radius=11,
                fg_color="transparent", text_color=MUTED, hover_color=PANEL_2,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), anchor="w",
                command=lambda p=label: self.show_page(p))
            btn.pack(fill="x", padx=14, pady=4)
            self.nav_buttons[label] = btn
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=21, pady=21)
        text(bottom, "●  Lokalne pomiary", 11, color=ACCENT, anchor="w").pack(fill="x")
        text(bottom, f"v{APP_VERSION}  •  Open source", 11, color=MUTED, anchor="w").pack(fill="x", pady=(5, 0))
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.page = None

    def show_page(self, page_name: str):
        self.active_page = page_name
        for label, btn in self.nav_buttons.items():
            selected = label == page_name
            btn.configure(fg_color=PANEL_2 if selected else "transparent",
                          text_color=ACCENT if selected else MUTED)
        if self.page is not None:
            self.page.destroy()
        self.page = ctk.CTkScrollableFrame(self.content, fg_color=BG, corner_radius=0,
                                           scrollbar_button_color=PANEL_2)
        self.page.grid(row=0, column=0, sticky="nsew", padx=(22, 14), pady=(10, 14))
        self.page.grid_columnconfigure(0, weight=1)
        if page_name == "Dashboard":
            self._page_dashboard()
        elif page_name == "Historia":
            self._page_history()
        elif page_name == "Ustawienia":
            self._page_settings()
        else:
            self._page_about()

    def _section_heading(self, heading: str, subtitle: str):
        text(self.page, heading, 28, "bold", anchor="w").grid(sticky="ew", pady=(13, 2))
        text(self.page, subtitle, 12, color=MUTED, anchor="w").grid(sticky="ew", pady=(0, 23))

    def _page_dashboard(self):
        header = ctk.CTkFrame(self.page, fg_color="transparent")
        header.grid(sticky="ew", pady=(10, 18))
        header.grid_columnconfigure(0, weight=1)
        title_area = ctk.CTkFrame(header, fg_color="transparent")
        title_area.grid(row=0, column=0, sticky="w")
        text(title_area, "Centrum monitorowania", 27, "bold").pack(anchor="w")
        text(title_area, "Stabilność połączenia w czasie rzeczywistym", 12, color=MUTED).pack(anchor="w", pady=(3, 0))
        btn_area = ctk.CTkFrame(header, fg_color="transparent")
        btn_area.grid(row=0, column=1, sticky="e")
        self.status_badge = text(btn_area, "●  Uruchamianie", 12, "bold", YELLOW)
        self.status_badge.pack(side="left", padx=(0, 15))
        self.toggle_btn = ctk.CTkButton(btn_area, text="⏸  Wstrzymaj", width=120, height=38,
                                        fg_color=PANEL_2, hover_color="#2A4059", text_color=TEXT,
                                        command=self._toggle_monitor)
        self.toggle_btn.pack(side="left")

        metrics = ctk.CTkFrame(self.page, fg_color="transparent")
        metrics.grid(sticky="ew", pady=(0, 17))
        for i in range(4):
            metrics.grid_columnconfigure(i, weight=1, uniform="metric")
        self.metric_labels = {}
        for index, (key, label, accent, initial) in enumerate([
            ("ping", "OPÓŹNIENIE", ACCENT, "— ms"),
            ("download", "POBIERANIE", BLUE, "0 B/s"),
            ("upload", "WYSYŁANIE", BLUE, "0 B/s"),
            ("loss", "UTRATA ODPOWIEDZI", YELLOW, "0%")
        ]):
            panel = card(metrics, height=121)
            panel.grid(row=0, column=index, sticky="nsew", padx=(0, 10) if index < 3 else 0)
            panel.grid_propagate(False)
            text(panel, label, 10, "bold", MUTED, anchor="w").pack(fill="x", padx=17, pady=(17, 9))
            val = text(panel, initial, 25, "bold", accent, anchor="w")
            val.pack(fill="x", padx=17)
            self.metric_labels[key] = val

        grid = ctk.CTkFrame(self.page, fg_color="transparent")
        grid.grid(sticky="nsew")
        grid.grid_columnconfigure(0, weight=3)
        grid.grid_columnconfigure(1, weight=2)
        plot_card = card(grid)
        plot_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        text(plot_card, "Historia opóźnienia", 17, "bold", anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        text(plot_card, "Ostatnie 90 pomiarów • ms • czerwony = brak odpowiedzi", 11,
             color=MUTED, anchor="w").pack(fill="x", padx=18)
        self.chart = LatencyChart(plot_card, height=210)
        self.chart.pack(fill="both", expand=True, padx=(13, 14), pady=(12, 8))

        detail = card(grid)
        detail.grid(row=0, column=1, sticky="nsew")
        text(detail, "Jakość połączenia", 17, "bold", anchor="w").pack(fill="x", padx=18, pady=(16, 17))
        self.details = {}
        for name, default in [
            ("Cel testu", self.settings.target),
            ("Metoda", self.settings.protocol),
            ("Jitter", "— ms"),
            ("Wyniki sesji", "0 / 0"),
            ("Interfejs", self.settings.interface),
        ]:
            row = ctk.CTkFrame(detail, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=5)
            text(row, name, 11, color=MUTED).pack(side="left")
            value = text(row, default, 11, "bold")
            value.pack(side="right")
            self.details[name] = value
        text(detail, "* Ruch sieciowy ≠ maksymalna prędkość łącza.", 10,
             color=MUTED, wraplength=260, justify="left").pack(anchor="w", padx=18, pady=(14, 15))

        notices = card(self.page)
        notices.grid(sticky="ew", pady=(16, 0))
        title = ctk.CTkFrame(notices, fg_color="transparent")
        title.pack(fill="x", padx=18, pady=(13, 8))
        text(title, "Ostatnie zdarzenia", 17, "bold").pack(side="left")
        ctk.CTkButton(title, text="Cała historia  →", width=115, height=28, fg_color="transparent",
                      hover_color=PANEL_2, text_color=ACCENT,
                      command=lambda: self.show_page("Historia")).pack(side="right")
        self.dashboard_events = ctk.CTkFrame(notices, fg_color="transparent")
        self.dashboard_events.pack(fill="x", padx=18, pady=(0, 15))
        self._render_dashboard_events()
        # Rebuild the plot after navigating away and back.
        try:
            recent = list(reversed(self.store.recent_samples(90)))
            self.chart.samples.extend(
                latency if ok else None
                for _when, target, protocol, ok, latency, _rx, _tx in recent
                if target == self.settings.target and protocol == self.settings.protocol
            )
            self.chart.draw()
        except OSError:
            pass
        if self.last_sample:
            self._update_sample(self.last_sample, add_to_chart=False)
        self._update_status(bool(self.monitor and self.monitor.running))

    def _render_dashboard_events(self):
        if self.active_page != "Dashboard":
            return
        for child in self.dashboard_events.winfo_children():
            child.destroy()
        try:
            rows = self.store.recent_events(4)
        except OSError:
            rows = []
        if not rows:
            text(self.dashboard_events, "Brak zdarzeń. Monitor działa w tle.", 12, color=MUTED,
                 anchor="w").pack(fill="x", pady=7)
            return
        for when, category, message in rows:
            row = ctk.CTkFrame(self.dashboard_events, fg_color=PANEL_2, corner_radius=9)
            row.pack(fill="x", pady=3)
            shade = RED if "Brak" in category else (YELLOW if "Wysokie" in category else ACCENT)
            text(row, "●", 12, color=shade).pack(side="left", padx=(12, 9), pady=9)
            text(row, f"{category} — {message}", 11, anchor="w").pack(side="left", fill="x", expand=True)
            text(row, local_time(when), 10, color=MUTED).pack(side="right", padx=11)

    def _page_history(self):
        self._section_heading("Historia pomiarów", "Dane zapisane lokalnie na komputerze • ostatnie 30 dni")
        top = card(self.page)
        top.grid(sticky="ew", pady=(0, 15))
        line = ctk.CTkFrame(top, fg_color="transparent")
        line.pack(fill="x", padx=18, pady=15)
        try:
            samples, events = self.store.counts()
        except OSError:
            samples, events = 0, 0
        text(line, f"{samples:,} pomiarów   •   {events} zdarzeń", 14, "bold").pack(side="left")
        ctk.CTkButton(line, text="Eksport CSV", width=125, height=34, fg_color=ACCENT,
                      hover_color="#35C4A2", text_color=BG, command=self._export_csv).pack(side="right")

        events_card = card(self.page)
        events_card.grid(sticky="ew", pady=(0, 14))
        text(events_card, "Dziennik zdarzeń", 18, "bold", anchor="w").pack(fill="x", padx=18, pady=(17, 10))
        try:
            rows = self.store.recent_events(35)
        except OSError:
            rows = []
        if not rows:
            text(events_card, "Brak zarejestrowanych zdarzeń.", color=MUTED).pack(pady=16)
        for when, category, msg in rows:
            box = ctk.CTkFrame(events_card, fg_color=PANEL_2, corner_radius=8)
            box.pack(fill="x", padx=16, pady=3)
            text(box, local_time(when), 11, color=MUTED).pack(side="left", padx=12, pady=9)
            text(box, category, 11, "bold", RED if "Brak" in category else ACCENT).pack(side="left", padx=8)
            text(box, msg, 11).pack(side="left", padx=8)
        ctk.CTkFrame(events_card, fg_color="transparent", height=13).pack()

        samples_card = card(self.page)
        samples_card.grid(sticky="ew")
        text(samples_card, "Ostatnie pomiary", 18, "bold", anchor="w").pack(fill="x", padx=18, pady=(17, 12))
        try:
            recent = self.store.recent_samples(40)
        except OSError:
            recent = []
        if not recent:
            text(samples_card, "Pierwsze pomiary pojawią się tutaj.", color=MUTED).pack(pady=15)
        for when, host, protocol, ok, latency, rx, tx in recent:
            row = ctk.CTkFrame(samples_card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=4)
            text(row, local_time(when), 11, color=MUTED, width=120, anchor="w").pack(side="left")
            text(row, f"{host} [{protocol}]", 11, width=165, anchor="w").pack(side="left")
            text(row, f"{latency:.1f} ms" if ok and latency is not None else "Brak odpowiedzi",
                 11, "bold", ACCENT if ok else RED, width=137, anchor="w").pack(side="left")
            text(row, f"↓ {format_rate(rx)}    ↑ {format_rate(tx)}", 11, color=MUTED).pack(side="left")
        ctk.CTkFrame(samples_card, fg_color="transparent", height=12).pack()

    def _page_settings(self):
        self._section_heading("Ustawienia", "Zmień cel i sposób pomiaru • zapis lokalny")
        box = card(self.page)
        box.grid(sticky="ew")
        box.grid_columnconfigure(1, weight=1)

        def field_label(row: int, name: str, hint: str):
            left = ctk.CTkFrame(box, fg_color="transparent")
            left.grid(row=row, column=0, sticky="w", padx=(22, 27), pady=15)
            text(left, name, 14, "bold", anchor="w").pack(anchor="w")
            text(left, hint, 11, color=MUTED, anchor="w").pack(anchor="w", pady=(3, 0))

        field_label(0, "Adres do testowania", "Adres IP lub domena")
        self.target_entry = ctk.CTkEntry(box, height=39, fg_color=PANEL_2, border_color=BORDER)
        self.target_entry.grid(row=0, column=1, sticky="ew", padx=(0, 24))
        self.target_entry.insert(0, self.settings.target)

        field_label(1, "Metoda pomiaru", "ICMP = ping; TCP = połączenie z portem 443")
        self.protocol_var = ctk.StringVar(value=self.settings.protocol)
        ctk.CTkOptionMenu(box, values=["ICMP", "TCP"], variable=self.protocol_var,
                          fg_color=PANEL_2, button_color="#314562", height=39).grid(
                              row=1, column=1, sticky="ew", padx=(0, 24))

        field_label(2, "Częstotliwość", "Odstęp między kolejnymi pomiarami")
        self.interval_var = ctk.StringVar(value=str(self.settings.interval))
        ctk.CTkOptionMenu(box, values=["2", "3", "5", "10"], variable=self.interval_var,
                          fg_color=PANEL_2, button_color="#314562", height=39).grid(
                              row=2, column=1, sticky="ew", padx=(0, 24))

        field_label(3, "Interfejs sieciowy", "Źródło statystyk pobierania / wysyłania")
        self.interface_var = ctk.StringVar(value=self.settings.interface)
        available = ["Wszystkie", *available_interfaces()]
        if self.settings.interface not in available:
            available.append(self.settings.interface)
        ctk.CTkOptionMenu(box, values=available, variable=self.interface_var,
                          fg_color=PANEL_2, button_color="#314562", height=39).grid(
                              row=3, column=1, sticky="ew", padx=(0, 24))

        field_label(4, "Alert opóźnienia", "Trzy kolejne pomiary powyżej progu (ms)")
        self.threshold_entry = ctk.CTkEntry(box, height=39, fg_color=PANEL_2, border_color=BORDER)
        self.threshold_entry.grid(row=4, column=1, sticky="ew", padx=(0, 24))
        self.threshold_entry.insert(0, str(self.settings.latency_alert))

        field_label(5, "Powiadomienia", "Zdarzenia w aplikacji i na Windows (jeśli dostępne)")
        self.notifications_var = ctk.BooleanVar(value=self.settings.notifications)
        ctk.CTkSwitch(box, text="Włączone", variable=self.notifications_var,
                      progress_color=ACCENT).grid(row=5, column=1, sticky="w", padx=(0, 24))
        ctk.CTkFrame(box, fg_color="transparent", height=12).grid(row=6, column=0)

        btn = ctk.CTkButton(self.page, text="Zapisz i uruchom ponownie monitoring", height=43,
                            fg_color=ACCENT, hover_color="#35C4A2", text_color=BG,
                            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                            command=self._save_settings)
        btn.grid(sticky="w", pady=19)
        note = card(self.page)
        note.grid(sticky="ew", pady=(0, 15))
        text(note, "Ważne", 14, "bold", YELLOW, anchor="w").pack(fill="x", padx=18, pady=(13, 5))
        text(note, "ICMP bywa blokowany przez router lub serwer, co nie musi oznaczać awarii internetu. "
             "Tryb TCP sprawdza osiągalność portu 443. Prędkości ↓/↑ oznaczają aktualny ruch "
             "sieciowy, a nie wynik testu przepustowości łącza.",
             12, color=MUTED, wraplength=700, justify="left", anchor="w").pack(fill="x", padx=18, pady=(0, 15))

    def _page_about(self):
        self._section_heading("O NetPulse", "Darmowy monitor stabilności sieci dla Windows 10 i 11")
        panel = card(self.page)
        panel.grid(sticky="ew")
        text(panel, "◉  NetPulse", 31, "bold", ACCENT, anchor="w").pack(fill="x", padx=22, pady=(22, 8))
        for line in [
            f"Wersja: {APP_VERSION}",
            "Otwarte oprogramowanie • licencja MIT",
            "Pomiary ICMP / TCP, transfer sieciowy, jitter i historia zdarzeń.",
            "Brak reklam, konta użytkownika i zdalnej telemetrii.",
            "Program nie przechwytuje pakietów i nie zmienia rejestru systemu.",
            f"Dane aplikacji: {data_dir()}",
        ]:
            text(panel, line, 12, color=MUTED, anchor="w", wraplength=700,
                 justify="left").pack(fill="x", padx=22, pady=6)
        ctk.CTkFrame(panel, fg_color="transparent", height=16).pack()

    def _start_monitor(self):
        self.session_count = self.session_failures = 0
        self.monitor = Monitor(self.settings, self.store, self.event_queue)
        self.monitor.start()
        if self.active_page == "Dashboard":
            self.chart.reset()
            self._update_status(True)

    def _toggle_monitor(self):
        if self.monitor and self.monitor.running:
            self.monitor.stop()
            self._update_status(False)
        else:
            self._start_monitor()

    def _update_status(self, running: bool):
        if self.active_page != "Dashboard":
            return
        self.status_badge.configure(text="●  Monitorowanie" if running else "●  Wstrzymano",
                                    text_color=ACCENT if running else YELLOW)
        self.toggle_btn.configure(text="⏸  Wstrzymaj" if running else "▶  Wznów")

    def _save_settings(self):
        try:
            changed = Settings(
                target=self.target_entry.get(), protocol=self.protocol_var.get(),
                interval=int(self.interval_var.get()), interface=self.interface_var.get(),
                notifications=self.notifications_var.get(), latency_alert=int(self.threshold_entry.get()),
            )
            changed.validate()
            save_settings(changed)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Błąd ustawień", str(exc), parent=self)
            return
        if self.monitor:
            self.monitor.stop()
        self.settings = changed
        self.last_sample = None
        self._start_monitor()
        self.show_page("Dashboard")
        messagebox.showinfo("NetPulse", "Ustawienia zapisane. Monitoring uruchomiono ponownie.", parent=self)

    def _update_sample(self, sample: Sample, add_to_chart: bool = True):
        if self.active_page != "Dashboard":
            return
        result = sample.probe
        self.metric_labels["ping"].configure(text=f"{result.latency_ms:.1f} ms" if result.ok and result.latency_ms is not None else "Brak",
                                             text_color=ACCENT if result.ok else RED)
        self.metric_labels["download"].configure(text=format_rate(sample.download_bps))
        self.metric_labels["upload"].configure(text=format_rate(sample.upload_bps))
        self.metric_labels["loss"].configure(text=f"{sample.loss_pct:.1f}%",
                                             text_color=YELLOW if sample.loss_pct < 10 else RED)
        self.details["Cel testu"].configure(text=self.settings.target[:26])
        self.details["Metoda"].configure(text=self.settings.protocol)
        self.details["Jitter"].configure(text=(f"{sample.jitter_ms:.1f} ms" if sample.jitter_ms is not None else "— ms"))
        self.details["Wyniki sesji"].configure(text=f"{sample.total - sample.failed} / {sample.total}")
        self.details["Interfejs"].configure(text=self.settings.interface[:24])
        if add_to_chart:
            self.chart.add(result.latency_ms if result.ok else None)

    def _poll_queue(self):
        try:
            # Batch UI rendering to avoid accumulation after window was minimized.
            for _ in range(130):
                kind, payload = self.event_queue.get_nowait()
                if kind == "sample":
                    self.last_sample = payload
                    self._update_sample(payload)
                elif kind == "event":
                    _when, title, content, should_notify = payload
                    if self.active_page == "Dashboard":
                        self._render_dashboard_events()
                    if should_notify and self.settings.notifications:
                        self._notify(title, content)
                elif kind in ("error", "interface_error", "storage_error"):
                    if payload != self.last_error:
                        self.last_error = payload
                        if self.active_page == "Dashboard":
                            self.status_badge.configure(text="●  Uwaga", text_color=YELLOW)
                elif kind == "state":
                    # Prevent an old monitor's delayed 'stopped' state from hiding the new status.
                    if self.monitor:
                        self._update_status(self.monitor.running)
        except Empty:
            pass
        self.after(250, self._poll_queue)

    def _notify(self, title: str, message: str):
        # Windows toast is best-effort; all alerts remain available in History.
        try:
            from winotify import Notification
            Notification(app_id="NetPulse", title=title, msg=message).show()
        except Exception:
            pass

    def _export_csv(self):
        default_name = f"NetPulse_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
        target = filedialog.asksaveasfilename(parent=self, title="Eksport historii",
                                               defaultextension=".csv", initialfile=default_name,
                                               filetypes=[("CSV", "*.csv")])
        if not target:
            return
        try:
            n = self.store.export_csv(Path(target))
            messagebox.showinfo("Eksport zakończony", f"Zapisano {n} pomiarów do pliku CSV.", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Błąd eksportu", str(exc), parent=self)

    def _close(self):
        if self.monitor:
            self.monitor.stop()
        self.destroy()


def run_app():
    app = NetPulseApp()
    app.mainloop()
