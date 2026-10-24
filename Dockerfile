# ---------- Stage 1: build the 3D website (Vite) ----------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python runtime (FastAPI + models) ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# libgomp1 = OpenMP runtime required by LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# application code + runtime artifacts only (no training data, candidates or raw GLB originals)
COPY main.py ./
COPY backend/ backend/
COPY src/ src/
COPY models/binary_model.joblib models/multiclass_model.joblib models/
COPY data/KDDTest+.txt data/
COPY reports/ reports/
COPY --from=frontend /app/frontend/dist frontend/dist

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
