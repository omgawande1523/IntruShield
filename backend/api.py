"""IntruShield product site backend - FastAPI.

Serves the real trained models (models/*.joblib), the evaluation numbers (reports/metrics.json)
and curated KDDTest+ rows for the live demo. Nothing in src/, models/ or reports/ is modified.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore")

from config import CATEGORICAL, FEATURES, MODELS_DIR, REPORTS_DIR  # noqa: E402
from data import load_split  # noqa: E402

try:
    import shap
except Exception:  # noqa: BLE001
    shap = None

# --------------------------------------------------------------------------- plain-English maps
FRIENDLY = {
    "duration": "connection duration",
    "protocol_type": "network protocol",
    "service": "service being contacted",
    "flag": "connection status flag",
    "src_bytes": "amount of data sent",
    "dst_bytes": "amount of data received",
    "land": "source and destination identical",
    "wrong_fragment": "malformed packet fragments",
    "urgent": "urgent packets",
    "hot": "suspicious 'hot' indicators",
    "num_failed_logins": "failed login attempts",
    "logged_in": "successfully logged in",
    "num_compromised": "compromised conditions",
    "root_shell": "root shell obtained",
    "su_attempted": "attempted to become admin",
    "num_root": "admin-level operations",
    "num_file_creations": "files created",
    "num_shells": "shell prompts opened",
    "num_access_files": "access-control files touched",
    "num_outbound_cmds": "outbound commands",
    "is_host_login": "login to a host account",
    "is_guest_login": "guest login",
    "count": "connections in the last 2 seconds",
    "srv_count": "connections to this service in the last 2 seconds",
    "serror_rate": "failed-handshake rate",
    "srv_serror_rate": "failed handshakes to this service",
    "rerror_rate": "rejected-connection rate",
    "srv_rerror_rate": "rejections from this service",
    "same_srv_rate": "share of connections to the same service",
    "diff_srv_rate": "share of connections to different services",
    "srv_diff_host_rate": "same service, different hosts",
    "dst_host_count": "connections to this host recently",
    "dst_host_srv_count": "connections to this host's service recently",
    "dst_host_same_srv_rate": "host traffic on the same service",
    "dst_host_diff_srv_rate": "host traffic across many services",
    "dst_host_same_src_port_rate": "host traffic from the same source port",
    "dst_host_srv_diff_host_rate": "this service reached from many hosts",
    "dst_host_serror_rate": "failed handshakes to this host",
    "dst_host_srv_serror_rate": "failed handshakes to this service",
    "dst_host_rerror_rate": "rejections from this host",
    "dst_host_srv_rerror_rate": "rejections from this host's service",
}
FAMILY = {
    "Normal": "Ordinary, legitimate traffic.",
    "DoS": "Denial of service: flooding a server so real users cannot get through.",
    "Probe": "Reconnaissance: scanning the network to find open doors before an attack.",
    "R2L": "Remote break-in: an outsider trying to get in, e.g. by guessing passwords.",
    "U2R": "Privilege escalation: a logged-in user trying to seize admin control.",
}
ATTACK_BLURB = {
    "neptune": "SYN flood", "smurf": "ICMP flood", "back": "web-server flood", "teardrop": "fragment attack",
    "pod": "ping of death", "land": "self-addressed packets", "apache2": "web-server flood",
    "mailbomb": "mail flood", "processtable": "process exhaustion", "udpstorm": "UDP storm",
    "ipsweep": "ping sweep", "nmap": "port scan", "portsweep": "port sweep", "satan": "vulnerability scan",
    "mscan": "multi-service scan", "saint": "vulnerability scan", "guess_passwd": "password guessing",
    "warezmaster": "illegal upload", "warezclient": "illegal download", "ftp_write": "FTP write abuse",
    "imap": "mail-server exploit", "phf": "CGI exploit", "multihop": "multi-hop break-in", "spy": "spying",
    "named": "DNS exploit", "sendmail": "mail exploit", "snmpgetattack": "SNMP snooping",
    "snmpguess": "SNMP password guessing", "xlock": "screen-lock trick", "xsnoop": "keystroke snooping",
    "worm": "worm", "buffer_overflow": "buffer overflow", "loadmodule": "module injection",
    "perl": "perl exploit", "rootkit": "rootkit", "httptunnel": "hidden tunnel", "ps": "process exploit",
    "sqlattack": "SQL exploit", "xterm": "terminal exploit", "normal": "normal traffic",
}

# --------------------------------------------------------------------------- state
S: dict[str, Any] = {}


def _feature_from_name(name: str) -> str:
    """Map a preprocessed feature name (e.g. 'service_http', 'num__count') back to a raw feature."""
    for pre in ("num__", "cat__", "remainder__"):
        if name.startswith(pre):
            name = name[len(pre):]
    if name in FEATURES:
        return name
    for c in CATEGORICAL:
        if name.startswith(c + "_"):
            return c
    return name


def _num(v):
    v = float(v)
    return int(v) if v.is_integer() else v


def _load() -> None:
    t0 = time.perf_counter()
    binary = joblib.load(MODELS_DIR / "binary_model.joblib")
    multi = joblib.load(MODELS_DIR / "multiclass_model.joblib")
    metrics = json.loads((REPORTS_DIR / "metrics.json").read_text())
    audit_f = REPORTS_DIR / "audit.json"
    audit = json.loads(audit_f.read_text()) if audit_f.exists() else {}
    test = load_split("test").reset_index(drop=True)
    # Attack types absent from KDDTrain+ are listed in reports/audit.json; everything else was seen.
    unseen = set(audit.get("attacks_in_test_not_in_train", {}))
    test["seen_in_train"] = ~test["attack"].isin(unseen)

    pipe = binary["pipeline"]
    clf, prep = pipe["clf"], pipe["prep"]
    explainer = None
    if shap is not None and not hasattr(clf, "coef_"):
        explainer = shap.TreeExplainer(clf)
    names = [str(n) for n in prep.get_feature_names_out()]

    # score the whole test set once (for curated-row selection)
    p = pipe.predict_proba(test[FEATURES])[:, 1]
    test["p_attack"] = p
    test["pred_attack"] = p >= binary["threshold"]
    test["pred_class"] = multi["label_encoder"].inverse_transform(multi["pipeline"].predict(test[FEATURES]))
    baseline = test[(test["label5"] == "Normal") & (~test["pred_attack"]) & (test["service"] == "http")]
    baseline = baseline.sample(1, random_state=42).iloc[0]

    S.update(binary=binary, multi=multi, pipe=pipe, clf=clf, prep=prep, explainer=explainer,
             names=names, metrics=metrics, audit=audit, test=test, baseline=baseline,
             threshold=float(binary["threshold"]))
    S["samples"] = _curate(test)
    S["services"] = sorted(test["service"].unique().tolist())
    S["loaded_s"] = round(time.perf_counter() - t0, 2)


def _curate(test: pd.DataFrame) -> list[dict]:
    """Pick real KDDTest+ rows for the demo chips (deterministic, random_state=42)."""
    specs = [
        ("normal_1", "Normal: web browsing", dict(attack="normal", service="http", correct=True)),
        ("normal_2", "Normal: file transfer", dict(attack="normal", service="ftp_data", correct=True)),
        ("dos", "DoS flood", dict(attack="neptune", correct=True)),
        ("probe", "Network scan", dict(attack="satan", correct=True)),
        ("r2l", "Remote break-in", dict(attack="warezmaster", correct=True)),
        ("u2r", "Privilege escalation", dict(attack="buffer_overflow", correct=True)),
        ("unseen", "Never seen in training", dict(attack="mscan", correct=True)),
        ("hard", "Stealthy password guess", dict(attack="guess_passwd", correct=False)),
    ]
    out = []
    for sid, title, sp in specs:
        df = test[test["attack"] == sp["attack"]]
        if "service" in sp:
            df2 = df[df["service"] == sp["service"]]
            df = df2 if len(df2) else df
        is_att = sp["attack"] != "normal"
        want = (df["pred_attack"] == is_att) if sp["correct"] else (df["pred_attack"] != is_att)
        df2 = df[want]
        df = df2 if len(df2) else df
        if sp["correct"] and is_att:  # prefer rows where the family is also identified correctly
            df3 = df[df["pred_class"] == df["label5"]]
            df = df3 if len(df3) else df
        if not len(df):
            continue
        row = df.sample(1, random_state=42).iloc[0]
        feats = {f: (row[f] if f in CATEGORICAL else _num(row[f])) for f in FEATURES}
        out.append({
            "id": sid,
            "title": title,
            "true_class": row["label5"],
            "attack_name": row["attack"],
            "attack_blurb": ATTACK_BLURB.get(row["attack"], row["attack"]),
            "seen_in_train": bool(row["seen_in_train"]),
            "row_index": int(row.name),
            "features": feats,
        })
    return out


# --------------------------------------------------------------------------- scoring
def _score(df: pd.DataFrame, explain: bool = True) -> list[dict]:
    X = df[FEATURES]
    t0 = time.perf_counter()
    p = S["pipe"].predict_proba(X)[:, 1]
    is_attack = p >= S["threshold"]
    mproba = S["multi"]["pipeline"].predict_proba(X)
    mclasses = list(S["multi"]["label_encoder"].classes_)
    cls = [mclasses[k] for k in mproba.argmax(1)]
    fam_conf = mproba.max(1)
    # binary says attack but family model says Normal -> report the most likely attack family
    not_normal = [k for k, c in enumerate(mclasses) if c != "Normal"]
    for i in range(len(df)):
        if is_attack[i] and cls[i] == "Normal":
            k = max(not_normal, key=lambda k: mproba[i, k])
            cls[i] = mclasses[k]
            fam_conf[i] = mproba[i, k]
    latency_ms = (time.perf_counter() - t0) * 1000.0 / max(len(df), 1)

    reasons_all = [[] for _ in range(len(df))]
    if explain:
        Xt = S["prep"].transform(X)
        if hasattr(Xt, "toarray"):
            Xt = Xt.toarray()
        if S["explainer"] is not None:
            sv = S["explainer"].shap_values(Xt)
            if isinstance(sv, list):
                sv = sv[1]
            elif getattr(sv, "ndim", 2) == 3:
                sv = sv[:, :, 1]
        else:
            sv = Xt * S["clf"].coef_[0]
        names = S["names"]
        for i in range(len(df)):
            order = np.argsort(-np.abs(sv[i]))[:3]
            top_abs = float(abs(sv[i][order[0]])) or 1.0
            rs = []
            for j in order:
                raw = _feature_from_name(names[j])
                val = X.iloc[i][raw]
                rs.append({
                    "feature": names[j],
                    "raw_feature": raw,
                    "friendly_label": FRIENDLY.get(raw, raw.replace("_", " ")),
                    "value": val if raw in CATEGORICAL else _num(val),
                    "direction": "attack" if sv[i][j] > 0 else "normal",
                    "shap": round(float(sv[i][j]), 4),
                    "strength": round(float(abs(sv[i][j])) / top_abs, 3),
                })
            reasons_all[i] = rs

    out = []
    for i in range(len(df)):
        verdict = "ATTACK" if is_attack[i] else "NORMAL"
        pred_class = str(cls[i]) if is_attack[i] else "Normal"
        out.append({
            "verdict": verdict,
            "probability": round(float(p[i]), 6),
            "threshold": S["threshold"],
            "pred_class": pred_class,
            "family": FAMILY.get(pred_class, ""),
            "family_confidence": round(float(fam_conf[i]), 4),
            "reasons": reasons_all[i],
            "latency_ms": round(latency_ms, 3),
        })
    return out


def _coerce_features(feats: dict) -> tuple[dict, list[str]]:
    """Fill missing features from a normal baseline row; validate types."""
    base = S["baseline"]
    row, warns = {}, []
    for f in FEATURES:
        v = feats.get(f, None)
        if v is None:
            row[f] = base[f] if f in CATEGORICAL else _num(base[f])
            continue
        if f in CATEGORICAL:
            row[f] = str(v).strip()
        else:
            try:
                row[f] = float(v)
            except (TypeError, ValueError):
                raise HTTPException(422, f"Feature '{f}' must be numeric, got {v!r}")
            if not np.isfinite(row[f]) or row[f] < 0:
                raise HTTPException(422, f"Feature '{f}' must be a finite non-negative number")
    extra = sorted(set(feats) - set(FEATURES))
    if extra:
        warns.append(f"ignored unknown features: {extra[:5]}")
    return row, warns


# --------------------------------------------------------------------------- API
class PredictBody(BaseModel):
    features: dict[str, Any] | None = Field(default=None, description="Any subset of the 41 features")
    sample_id: str | None = None

    @model_validator(mode="after")
    def _one_of(self):
        if self.features is None and self.sample_id is None:
            raise ValueError("Provide 'features' or 'sample_id'")
        return self


app = FastAPI(title="IntruShield API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def _cache_headers(request: Request, call_next):
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/") or path.startswith("/models/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    elif resp.headers.get("content-type", "").startswith("text/html"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.on_event("startup")
def _startup():
    _load()


@app.exception_handler(Exception)
async def _any_error(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": type(exc).__name__, "detail": str(exc)[:300]})


@app.get("/api/health")
def health():
    return {"ok": True, "binary_model": S["binary"]["model_name"], "multiclass_model": S["multi"]["model_name"],
            "threshold": S["threshold"], "test_rows": int(len(S["test"])), "shap": S["explainer"] is not None,
            "load_time_s": S["loaded_s"]}


@app.get("/api/metrics")
def metrics():
    m = S["metrics"]
    dep_b = m["deployed"]["binary"]["B: KDDTest+"]
    dep_m = m["deployed"]["multiclass"]["B: KDDTest+"]
    svu = m["seen_vs_unseen"].get("deployed") or m["seen_vs_unseen"][m["best"]["binary"]]
    t = S["test"]
    return {
        "model": {"binary": m["deployed"]["binary"]["model"], "multiclass": m["deployed"]["multiclass"]["model"],
                  "size_mb": m["deployed"]["binary"]["size_mb"]},
        "test_set": {"rows": int(len(t)), "attacks": int(t["is_attack"].sum()),
                     "normal": int((t["is_attack"] == 0).sum()),
                     "attack_types": int(t["attack"].nunique()),
                     "unseen_attack_types": int(t.loc[~t["seen_in_train"], "attack"].nunique()),
                     "unseen_attack_rows": int((~t["seen_in_train"] & (t["is_attack"] == 1)).sum()),
                     "train_rows": S["audit"].get("rows", {}).get("train")},
        "detection_rate": dep_b["recall"],
        "unseen_detection_rate": svu["unseen"]["recall"],
        "seen_detection_rate": svu["seen"]["recall"],
        "unseen_n": svu["unseen"]["n"],
        "roc_auc": dep_b["roc_auc"],
        "false_alarm_rate": dep_b["false_alarm_rate"],
        "precision": dep_b["precision"],
        "accuracy": dep_b["accuracy"],
        "inference_us_per_row": dep_b["inference_us_per_row"],
        "threshold": m["threshold"]["value"],
        "per_class_recall": dep_m["per_class_recall"],
        "cv5_binary": m["cv5"]["binary"],
        "n_features": len(FEATURES),
    }


@app.get("/api/samples")
def samples():
    base = S["baseline"]
    return {"samples": S["samples"], "services": S["services"],
            "baseline": {f: (base[f] if f in CATEGORICAL else _num(base[f])) for f in FEATURES}}


@app.post("/api/predict")
def predict(body: PredictBody):
    truth = None
    if body.sample_id is not None:
        s = next((x for x in S["samples"] if x["id"] == body.sample_id), None)
        if s is None:
            raise HTTPException(404, f"unknown sample_id '{body.sample_id}'")
        feats = dict(s["features"])
        if body.features:
            feats.update(body.features)
        truth = {"true_class": s["true_class"], "attack_name": s["attack_name"],
                 "attack_blurb": s["attack_blurb"], "seen_in_train": s["seen_in_train"]}
    else:
        feats = body.features or {}
    row, warns = _coerce_features(feats)
    res = _score(pd.DataFrame([row]))[0]
    res["features"] = row
    res["truth"] = truth
    if warns:
        res["warnings"] = warns
    return res


@app.get("/api/stream")
def stream(n: int = Query(8, ge=1, le=64)):
    rows = S["test"].sample(n=n)
    scored = _score(rows, explain=False)
    out = []
    for (idx, r), s in zip(rows.iterrows(), scored):
        truth_attack = bool(r["is_attack"])
        pred_attack = s["verdict"] == "ATTACK"
        out.append({
            "row_index": int(idx), "service": r["service"], "protocol": r["protocol_type"],
            "src_bytes": _num(r["src_bytes"]), "dst_bytes": _num(r["dst_bytes"]),
            "true_class": r["label5"], "attack_name": r["attack"], "seen_in_train": bool(r["seen_in_train"]),
            "verdict": s["verdict"], "pred_class": s["pred_class"], "probability": s["probability"],
            "outcome": ("caught" if truth_attack and pred_attack else "missed" if truth_attack else
                        "false_alarm" if pred_attack else "clean"),
        })
    return {"items": out}


@app.get("/report")
def report():
    f = REPORTS_DIR / "eval_report.html"
    if not f.exists():
        raise HTTPException(404, "report not generated yet")
    return FileResponse(f)


# figures referenced by the report (relative paths)
if (REPORTS_DIR / "figures").exists():
    app.mount("/figures", StaticFiles(directory=REPORTS_DIR / "figures"), name="figures")
    app.mount("/reports/figures", StaticFiles(directory=REPORTS_DIR / "figures"), name="figures2")
