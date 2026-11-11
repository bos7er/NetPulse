# ◉ NetPulse — Network Stability Monitor

**NetPulse** to darmowa aplikacja **Windows 10/11**, która na bieżąco pokazuje opóźnienie, brak odpowiedzi na testy sieciowe, jitter oraz faktyczny ruch sieciowy na komputerze. Program działa lokalnie, bez konta i bez telemetrii.

![License](https://img.shields.io/badge/license-MIT-47e5be?style=flat-square) ![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-6b9aff?style=flat-square) ![Python](https://img.shields.io/badge/Python-3.12-6b9aff?style=flat-square)

## ☕ Support NetPulse

If you like NetPulse, consider supporting its development!

[![Buy Me a Coffee](https://img.shields.io/badge/☕_Buy_Me_a_Coffee-Donate_via_PayPal-blue?style=for-the-badge)](https://www.paypal.me/bos7er)



## Funkcje

- **Ping ICMP** (klasyczny `ping`) lub **opóźnienie połączenia TCP** (port 443).
- Wykres opóźnienia w czasie rzeczywistym — 90 ostatnich pomiarów.
- Prędkość bieżącego pobierania i wysyłania danych w B/s, KB/s, MB/s.
- Procent nieudanych testów z ostatnich **60 pomiarów**, oraz średni jitter.
- Wykrywanie utraty odpowiedzi, odzyskania łączności i utrzymującego się wysokiego opóźnienia.
- Historia pomiarów i zdarzeń w lokalnej bazie SQLite (automatyczne usuwanie po 30 dniach).
- Eksport CSV, wybór interfejsu sieciowego i częstotliwości pomiarów.
- Powiadomienia Windows, gdy są dostępne; historia zdarzeń pozostaje w programie.
- Żadnych zmian rejestru, sterowników, DNS ani konfiguracji sieci.

## ⬇️ Pobieranie gotowego EXE

**Po opublikowaniu pierwszego wydania**: otwórz zakładkę **Releases** po prawej stronie repozytorium, a następnie pobierz **`NetPulse.exe`** z sekcji *Assets*. Nie jest wymagana instalacja Pythona.

Jeśli nie ma jeszcze wydania, przejdź do **Actions → Build NetPulse for Windows → Run workflow**, otwórz zakończony pomyślnie przebieg i pobierz artefakt **NetPulse-Windows-EXE**. Po rozpakowaniu otrzymasz `NetPulse.exe`.

> Aplikacja nie jest podpisana certyfikatem cyfrowym. Windows SmartScreen może wyświetlić ostrzeżenie w przypadku nowego lub mało znanego programu. Kod jest otwarty — sprawdź go przed uruchomieniem.

## Jak samodzielnie zbudować NetPulse.exe na Windows

1. Zainstaluj **Python 3.12** (zaznacz „Add Python to PATH”).
2. Pobierz repozytorium jako ZIP i rozpakuj je.
3. Uruchom plik **`build.bat`**.
4. Gotowy program znajdziesz w **`dist\NetPulse.exe`**.

Alternatywnie uruchom kod źródłowy:

```powershell
py -m pip install -r requirements.txt
py main.py
```

Testy automatyczne:

```powershell
py -m unittest discover -s tests -v
```

## Jak wrzucić projekt na GitHub

1. Utwórz nowe publiczne repozytorium o nazwie `NetPulse` (bez dodatkowego README i `.gitignore`).
2. Prześlij **zawartość** rozpakowanego folderu NetPulse (nie plik ZIP), w tym folder `.github/workflows`.
3. Po przesłaniu plików przejdź do **Actions**, wybierz **Build NetPulse for Windows** i w razie potrzeby kliknij **Run workflow**.
4. Aby plik EXE był na stałe dostępny w **Releases**, utwórz tag `v1.0.0` i wypchnij go do repozytorium — workflow automatycznie utworzy Release i dołączy EXE.

Przykładowe polecenia (zastąp `TWOJ_LOGIN`):

```bash
git init
git add .
git commit -m "NetPulse 1.0.0"
git branch -M main
git remote add origin https://github.com/TWOJ_LOGIN/NetPulse.git
git push -u origin main
git tag v1.0.0
git push origin v1.0.0
```

GitHub może wymagać zalogowania się przez przeglądarkę/Git Credential Manager.

## Jak czytać wyniki

- **ICMP** — mierzy opóźnienie odpowiedzi na ping. Niektóre serwery lub routery ignorują pakiety ICMP; brak odpowiedzi nie jest jednoznaczny z brakiem internetu.
- **TCP** — mierzy czas nawiązania połączenia z wybranym hostem na porcie 443, a nie pełny czas otwarcia strony WWW.
- **Utrata odpowiedzi (%)** — procent nieudanych testów w ruchomym oknie maksymalnie 60 ostatnich pomiarów, a nie pełny pomiar utraty wszystkich pakietów internetowych.
- **Pobieranie/wysyłanie** — faktyczny transfer danych przez komputer, a **nie test maksymalnej przepustowości**. Wybierz konkretny interfejs zamiast „Wszystkie”, by nie sumować kilku kart sieciowych.
- **Jitter** — średnia bezwzględna różnica pomiędzy kolejnymi udanymi pomiarami w aktualnym oknie.

## Prywatność i pliki

Nie zbieramy danych osobowych ani historii przeglądarki, nie monitorujemy pakietów, nie wysyłamy pomiarów do serwera autora. Oczywiście testy ICMP/TCP wysyłają żądania do **adresu wybranego przez użytkownika** (domyślnie `1.1.1.1`).

Ustawienia i historia zapisywane są pod:

```text
%LOCALAPPDATA%\NetPulse\settings.json
%LOCALAPPDATA%\NetPulse\history.sqlite3
```

Aby usunąć całą historię, zamknij program i usuń ten folder.

## Technologie

Python 3.12 • CustomTkinter • psutil • SQLite • PyInstaller • GitHub Actions.

## Zgłaszanie błędów

Otwórz zakładkę **Issues** w repozytorium i opisz wersję Windows, problem oraz kroki jego odtworzenia. Nie dołączaj prywatnych adresów IP lub danych z logów bez sprawdzenia.

## Licencja

MIT — szczegóły w pliku [LICENSE](LICENSE).
