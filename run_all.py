"""IntruShield - run the whole pipeline: data audit -> train -> evaluate -> report -> demo."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
STEPS = ["data.py", "train.py", "evaluate.py", "report.py", "predict.py", "workflow.py"]
MODEL_ORDER = ["LogisticRegression", "RandomForest", "XGBoost", "LightGBM"]


def main():
    t0 = time.perf_counter()
    timings = {}
    for step in STEPS:
        print(f"\n{'=' * 78}\n>>> python src/{step}\n{'=' * 78}", flush=True)
        t = time.perf_counter()
        rc = subprocess.call([PY, str(ROOT / "src" / step)], cwd=ROOT)
        timings[step] = time.perf_counter() - t
        if rc != 0:
            sys.exit(f"\nStep {step} failed with exit code {rc}. Aborting.")
    total = time.perf_counter() - t0

    M = json.loads((ROOT / "reports" / "metrics.json").read_text())
    P = M["protocols"]
    print(f"\n{'=' * 78}\nIntruShield - RESULTS SUMMARY\n{'=' * 78}")
    for task in ("binary", "multiclass"):
        print(f"\n{task.upper():<10}  {'Protocol A (validation)':^34} | {'Protocol B (KDDTest+)':^34} | B-21")
        print(f"{'model':<20}{'F1m':>8}{'Acc':>8}{'Recall':>8}{'FAR':>8} |{'F1m':>8}{'Acc':>8}{'Recall':>8}{'FAR':>8} |{'F1m':>8}")
        for n in MODEL_ORDER:
            a, b, c = P["A: validation"][task][n], P["B: KDDTest+"][task][n], P["B: KDDTest-21"][task][n]
            star = "*" if n == M["best"][task] else " "
            print(f"{star}{n:<19}{a['f1_macro']:>8.4f}{a['accuracy']:>8.4f}{a['recall']:>8.4f}{a['false_alarm_rate']:>8.4f} |"
                  f"{b['f1_macro']:>8.4f}{b['accuracy']:>8.4f}{b['recall']:>8.4f}{b['false_alarm_rate']:>8.4f} |{c['f1_macro']:>8.4f}")
    print("\n* = selected on validation macro-F1.  FAR = false-alarm rate on normal traffic.")
    db = M["deployed"]["binary"]["B: KDDTest+"]
    svu = M["seen_vs_unseen"]["deployed"]
    print(f"Deployed binary {M['best']['binary']} (thr {M['threshold']['value']:.3f}) on KDDTest+: recall {db['recall']:.4f}, "
          f"FAR {db['false_alarm_rate']:.4f}, AUC {db['roc_auc']:.4f} | seen-attack recall {svu['seen']['recall']:.3f}, "
          f"unseen-attack recall {svu['unseen']['recall']:.3f}")
    lk = M["leakage_check"]
    if lk["triggered"]:
        print(f"Leakage check: Protocol A accuracy {lk['max_protocol_a_accuracy']:.4%} > 99.9%; "
              f"{lk['val_rows_with_identical_feature_vector_in_train_split']} / {lk['val_rows']} validation rows duplicate a train row.")
    print("\nStep timings: " + ", ".join(f"{k} {v:.0f}s" for k, v in timings.items()) + f"  | TOTAL {total / 60:.1f} min")
    print(f"\nReport: {ROOT / 'reports' / 'eval_report.html'}")
    print(f"Workflow simulation: {ROOT / 'reports' / 'workflow_sim.html'}")


if __name__ == "__main__":
    main()
