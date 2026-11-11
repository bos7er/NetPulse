@echo off
setlocal
cd /d "%~dp0"
echo === NetPulse - budowanie pliku .exe ===
py -m pip install -r requirements.txt pyinstaller || goto :error
py -m PyInstaller --noconfirm --clean --onefile --windowed --collect-data customtkinter --name NetPulse --icon assets\netpulse.ico main.py || goto :error
echo.
echo GOTOWE: dist\NetPulse.exe
echo.
pause
exit /b 0
:error
echo.
echo BLAD: sprawdz czy masz Python 3.11+ i polaczenie z internetem.
pause
exit /b 1
