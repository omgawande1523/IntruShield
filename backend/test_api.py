"""Quick smoke test: hits every endpoint in-process via TestClient."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

import main as server  # noqa: E402  (full app: API + site)

with TestClient(server.app) as c:
    print("health", c.get("/api/health").json())
    m = c.get("/api/metrics").json()
    print("metrics", json.dumps(m)[:500])
    s = c.get("/api/samples").json()
    print(f"{len(s['samples'])} samples, {len(s['services'])} services")
    print(f"{'id':<10}{'truth':<8}{'attack':<16}{'seen':<6}{'verdict':<8}{'class':<8}{'p':>8} {'ms':>6}  reasons")
    for smp in s["samples"]:
        r = c.post("/api/predict", json={"sample_id": smp["id"]}).json()
        why = "; ".join(f"{x['friendly_label']}({x['direction'][0]})" for x in r["reasons"])
        print(f"{smp['id']:<10}{smp['true_class']:<8}{smp['attack_name']:<16}{str(smp['seen_in_train']):<6}"
              f"{r['verdict']:<8}{r['pred_class']:<8}{r['probability']:>8.4f} {r['latency_ms']:>6.2f}  {why}")
    r = c.post("/api/predict", json={"features": {"src_bytes": 0, "count": 500, "serror_rate": 1.0,
                                                   "dst_host_serror_rate": 1.0, "service": "private"}}).json()
    print("crafted flood ->", r["verdict"], r["pred_class"], r["probability"])
    r = c.post("/api/predict", json={"features": {}}).json()
    print("baseline ->", r["verdict"], r["probability"], r["features"]["service"], r["features"]["src_bytes"])
    r = c.post("/api/predict", json={"features": {"src_bytes": "abc"}})
    print("bad input ->", r.status_code, r.json())
    r = c.post("/api/predict", json={})
    print("empty ->", r.status_code)
    r = c.post("/api/predict", json={"features": {"service": "nonexistent_svc"}})
    print("unknown service ->", r.status_code, r.json().get("verdict"), r.json().get("detail"))
    t0 = time.perf_counter()
    st = c.get("/api/stream?n=8").json()
    print("stream", len(st["items"]), [i["outcome"] for i in st["items"]], f"{(time.perf_counter()-t0)*1000:.0f}ms")
    print("report", c.get("/report").status_code)
    print("site /", c.get("/").status_code, "| /models/brain.glb", c.get("/models/brain.glb").status_code)
