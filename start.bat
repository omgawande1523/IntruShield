@echo off
setlocal
cd /d "%~dp0"
title IntruShield

if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  py -3.12 -m venv .venv || python -m venv .venv
  .venv\Scripts\python.exe -m pip install -q -r requirements-ml.txt
)
.venv\Scripts\python.exe -c "import fastapi, uvicorn" 2>nul || .venv\Scripts\python.exe -m pip install -q -r requirements.txt

echo Building website...
pushd frontend
if not exist node_modules call npm ci --no-audit --no-fund
call npm run build || (popd & echo Frontend build failed & exit /b 1)
popd

start "" http://127.0.0.1:8000
.venv\Scripts\python.exe main.py
endlocal
