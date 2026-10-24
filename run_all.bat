@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creating venv...
  py -3.12 -m venv .venv || python -m venv .venv
  .venv\Scripts\python.exe -m pip install -q -r requirements-ml.txt
)
.venv\Scripts\python.exe run_all.py
endlocal
