# IntruShield - Network Intrusion Detection on NSL-KDD

Binary (normal vs attack) and 5-class (Normal / DoS / Probe / R2L / U2R) intrusion detection with a
leak-free, two-protocol evaluation (random validation split vs the official KDDTest+ / KDDTest-21).

## Run everything (CPU, < 25 min)

```
run_all.bat            # creates .venv on first run, installs requirements.txt, runs the pipeline
# or, with the venv active:
python run_all.py
```

Steps executed in order: `src/data.py` (download + audit) -> `src/train.py` (tune, select, CV,
threshold, refit) -> `src/evaluate.py` (metrics + figures) -> `src/report.py` (HTML report) ->
`src/predict.py` (10-row demo with SHAP reasons).

## Outputs

| Path | Content |
|---|---|
| `reports/eval_report.html` | self-contained report (figures embedded) |
| `reports/metrics.json` | every metric for every model under every protocol, error analysis, SHAP top-15 |
| `reports/audit.json` | data audit (rows, duplicates, class balance, unseen attack types) |
| `reports/train_summary.json` | tuning results, CV folds, threshold curve |
| `reports/figures/*.png` | all charts |
| `models/binary_model.joblib`, `models/multiclass_model.joblib` | deployable bundles: full pipeline + threshold + label encoder |
| `models/candidates/*.joblib` | the 8 split-trained candidate pipelines used for the comparison tables |

## Leakage rules enforced

* Preprocessing and models fit on KDDTrain+ only; KDDTest+ is first read in `evaluate.py`.
* Model selection, hyper-parameter search and the decision threshold use the 15 % validation split.
* `random_state=42` everywhere.

## Workflow simulation

`src/workflow.py` (last step of `run_all.py`) writes `reports/workflow_sim.html`: a self-contained, offline,
animated walk-through of the pipeline. It scores 400 random KDDTest+ rows with the saved models (plus top-3 SHAP
reasons for 30 of them) and embeds every number from `metrics.json` / `audit.json`. Controls: Space play/pause,
arrow keys for steps, R restart, speed 0.5x-4x, English/Hinglish captions, particles on/off. Open
`workflow_sim.html#7` to start at step 7; `?theme=light` forces light mode on a projector.

---

## Run the full app (website + live ML API)

`main.py` is the single entry point. One FastAPI process serves:

| URL | What |
|---|---|
| `/` | 3D product website (`frontend/dist`, built with Vite) |
| `/api/health`, `/api/metrics`, `/api/samples`, `/api/predict`, `/api/stream` | live ML API using `models/*.joblib` |
| `/report` | evaluation report (`reports/eval_report.html`) |

**Windows (one click):** `start.bat` creates the venv if needed, builds the website, and starts the app at http://127.0.0.1:8000

**Manual:**
```
pip install -r requirements.txt          # runtime only (requirements-ml.txt for training too)
cd frontend && npm ci && npm run build && cd ..
python main.py                           # http://127.0.0.1:8000
```

**Screenshot review** (needs the app running): `cd frontend && npx playwright install chromium && npm run shoot`
writes `design/screens/desktop-XX.png` (1440x900) and `mobile-XX.png` (390x844) and prints any page console errors.
It loads `/?shot`, which pauses the render loop and settles the 3D state deterministically, so it works on software GL.

## Project layout

```
IntruShield/
├── main.py                  # app entry point (API + website in one server)
├── requirements.txt         # runtime deps (Render/Docker)   · requirements-ml.txt = + training deps
├── Dockerfile, render.yaml  # deployment
├── src/                     # ML pipeline: config, data, features, train, evaluate, report, predict
├── models/                  # trained models (binary_model.joblib, multiclass_model.joblib)
├── data/                    # NSL-KDD (KDDTrain+, KDDTest+, KDDTest-21)
├── reports/                 # metrics.json, figures, eval_report.html, audit.json
├── backend/
│   ├── api.py               # FastAPI routes + model loading (/api/*, /report)
│   └── test_api.py          # smoke test of every endpoint: python backend/test_api.py
├── frontend/                # Vite + Three.js + GSAP website (src/, public/models/*.glb, scripts/shoot.mjs)
└── design/
    ├── reference/           # visual reference frames (not deployed)
    ├── source-models/       # unoptimised GLB originals (gitignored)
    └── screens/             # screenshot review output (gitignored)
```

## Deploy on Render

1. Push this folder to a GitHub repo (`.gitignore` already excludes `.venv`, `node_modules`,
   `frontend/dist`, `models/candidates` and the unoptimised GLB originals in `design/source-models`).
2. Render dashboard → **New → Blueprint** → pick the repo (uses `render.yaml`),
   or **New → Web Service** → pick the repo → Language **Docker**.
3. Render builds the `Dockerfile`: stage 1 builds the website with Node 22, stage 2 runs
   `uvicorn main:app` on Python 3.12 with the pinned versions the models were trained with.
4. Health check: `/api/health`. First deploy takes ~5–8 min; free instances sleep when idle
   (first request after sleep takes ~30–60 s). The app loads only KDDTest+ at runtime (training data is not shipped), so it fits the free plan's 512 MB.

3D model credits (CC BY 4.0, Sketchfab): brain by Yash_Dandavate · Earth by Akshat (shooter24994).
