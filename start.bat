@echo off
chcp 65001 >nul
title Smart Station - server (do not close)
cd /d "%~dp0app"
echo.
echo  === Smart Station: installing packages (first run 1-2 min) ===
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  ERROR: Python not found. Install Python 3.11+ from python.org
  echo  and tick "Add python.exe to PATH". Then run start.bat again.
  pause
  exit /b
)
echo.
set GROQ_API_KEY=
if exist "%~dp0groq_key.txt" (
  set /p GROQ_API_KEY=<"%~dp0groq_key.txt"
  echo  Groq key loaded from groq_key.txt
) else (
  set /p GROQ_API_KEY= Paste GROQ API key and press Enter, or just Enter to skip: 
)
echo.
echo  === Server started. Open http://localhost:8000 ===
echo  === Do NOT close this window during the demo ===
start "" http://localhost:8000
python -m uvicorn main:app --port 8000
echo.
echo  Server stopped. If you see an error above - send a screenshot.
pause
