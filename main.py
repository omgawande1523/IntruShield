"""IntruShield - application entry point (local and Render).

One process serves everything:
  /api/*            ML API (FastAPI)  -> backend/api.py, loads models/*.joblib at startup
  /report           evaluation report -> reports/eval_report.html
  /                 3D product website -> frontend/dist (Vite build)

Run locally:   python main.py                      -> http://127.0.0.1:8000
Run on Render: uvicorn main:app --host 0.0.0.0 --port $PORT   (see Dockerfile / render.yaml)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"

from backend.api import app  # noqa: E402  (all /api routes + model loading on startup)

# The built website is mounted last so every API route takes precedence.
if FRONTEND_DIST.joinpath("index.html").exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="site")
else:
    print("[IntruShield] Frontend build not found - run:  cd frontend && npm ci && npm run build",
          file=sys.stderr)


if __name__ == "__main__":
    import uvicorn

    on_server = "PORT" in os.environ          # Render (and most PaaS) set PORT
    host = os.getenv("HOST", "0.0.0.0" if on_server else "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"[IntruShield] http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}")
    uvicorn.run("main:app", host=host, port=port, proxy_headers=True, forwarded_allow_ips="*")
