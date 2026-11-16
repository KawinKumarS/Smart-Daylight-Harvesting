@echo off
cd /d "%~dp0"
echo Starting Smart Daylight Harvesting Dashboard...
echo Open http://127.0.0.1:8000 in your browser.
start "" http://127.0.0.1:8000
python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000
pause
