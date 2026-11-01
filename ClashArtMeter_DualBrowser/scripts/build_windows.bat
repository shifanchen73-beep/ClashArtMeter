@echo off
cd /d "%~dp0.."
python -m pip install "pyinstaller>=6.0,<7"
python -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
pyinstaller --noconfirm --clean --onefile --windowed --name ClashArtMeterDual --icon resources/app.ico app.py
if errorlevel 1 exit /b 1
echo Built: dist\ClashArtMeterDual.exe
pause
