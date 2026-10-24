"""IntruShield - generate reports/workflow_sim.html, an animated walk-through of the pipeline.

Read-only: metrics.json, audit.json, train_summary.json, the saved models and KDDTest+. Scores 400
random KDDTest+ rows (random_state=42) with the deployed models, computes top-3 SHAP reasons for
30 of them and embeds everything as one JSON blob in a self-contained HTML file.
"""
import json
import warnings

import joblib
import numpy as np

from config import CLASSES, FEATURES, MODELS_DIR, RANDOM_STATE, REPORTS_DIR, ROOT
from data import load_split
from predict import shap_reasons

warnings.filterwarnings("ignore")
TEMPLATE = ROOT / "src" / "workflow_template.html"
OUT = REPORTS_DIR / "workflow_sim.html"
N_ROWS, N_SHAP = 400, 30


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def main():
    M = json.loads((REPORTS_DIR / "metrics.json").read_text())
    A = json.loads((REPORTS_DIR / "audit.json").read_text())
    S = json.loads((REPORTS_DIR / "train_summary.json").read_text())
    binary = joblib.load(MODELS_DIR / "binary_model.joblib")
    multi = joblib.load(MODELS_DIR / "multiclass_model.joblib")
    le = multi["label_encoder"]
    thr = binary["threshold"]

    # ---- score 400 random KDDTest+ rows with the deployed models --------------------------------
    test = load_split("test")
    rows = test.sample(n=N_ROWS, random_state=RANDOM_STATE)
    X = rows[FEATURES]
    p_attack = binary["pipeline"].predict_proba(X)[:, 1]
    proba5 = multi["pipeline"].predict_proba(X)
    cls5 = le.inverse_transform(proba5.argmax(1))
    normal_idx = list(le.classes_).index("Normal")
    attack_only = proba5.copy()
    attack_only[:, normal_idx] = -1
    family = le.inverse_transform(attack_only.argmax(1))
    reasons = shap_reasons(binary["pipeline"], X.iloc[:N_SHAP])
    records = []
    for k, (_, r) in enumerate(rows.iterrows()):
        gate = bool(p_attack[k] >= thr)
        # hierarchical decision: the gate decides attack/normal; the 5-class model picks the family
        final = "Normal" if not gate else (cls5[k] if cls5[k] != "Normal" else family[k])
        rec = {"protocol": r["protocol_type"], "service": r["service"], "flag": r["flag"],
               "attack": r["attack"], "true": r["label5"], "p": round(float(p_attack[k]), 6),
               "gate": gate, "cls5": cls5[k], "final": final}
        if k < N_SHAP:
            rec["shap"] = [[f, round(v, 3), round(s, 3)] for f, v, s in reasons[k]]
        records.append(rec)
    n_feat_out = len(binary["pipeline"]["prep"].get_feature_names_out())

    # ---- numbers used by the scenes (all from the JSON files / saved models) -------------------
    P = M["protocols"]
    dep_b = M["deployed"]["binary"]["B: KDDTest+"]
    dep_m = M["deployed"]["multiclass"]["B: KDDTest+"]
    best_b, best_m = M["best"]["binary"], M["best"]["multiclass"]
    val_b = {n: P["A: validation"]["binary"][n]["f1_macro"] for n in M["model_meta"]["binary"]}
    val_m = {n: P["A: validation"]["multiclass"][n]["f1_macro"] for n in M["model_meta"]["multiclass"]}
    acc_a = P["A: validation"]["binary"][best_b]["accuracy"]
    svu = M["seen_vs_unseen"]["deployed"]
    unseen_types = len(A["attacks_in_test_not_in_train"])
    u2r_train = A["class_distribution"]["train"].get("U2R", 0)
    per_class = dep_m["per_class_recall"]
    missed = M["error_analysis"]["most_missed_binary"][:3]
    mc_pred = {r["attack"]: r["multiclass_most_common_prediction"]
               for r in M["error_analysis"]["per_attack_type"]}
    top8 = M["shap"]["top15"][:8]
    sens = M["threshold_sensitivity"]
    cv = M["cv5"]
    thr_info = M["threshold"]
    short = {"LogisticRegression": "LR", "RandomForest": "RF", "XGBoost": "XGB", "LightGBM": "LGBM"}

    nodes = {
        "raw": f"{A['rows']['train']:,} + {A['rows']['test']:,}",
        "audit": f"{unseen_types} unseen types",
        "prep": f"41 → {n_feat_out} features",
        **{f"m_{short[n]}": f"{val_b[n]:.3f} · {val_m[n]:.3f}" for n in short},
        "select": f"{short[best_b]} · CV {cv['binary']['mean']:.4f}",
        "gate": f"thr {thr:.2g}",
        **{f"c_{c}": pct(per_class[c], 0) + " recall" for c in CLASSES},
        "eval": f"acc {pct(dep_b['accuracy'])}",
        "explain": f"#1 {top8[0]['feature']}",
    }

    steps = [
        {"id": 1, "title": "Raw data", "nodes": ["raw"], "layer": 0,
         "en": f"NSL-KDD: {A['rows']['train']:,} training and {A['rows']['test']:,} test connections. "
               f"Each record is one network connection described by 41 features such as protocol, service, bytes and error rates.",
         "hi": f"NSL-KDD mein {A['rows']['train']:,} training aur {A['rows']['test']:,} test connections hain. "
               f"Har record ek network connection hai, jise 41 features describe karte hain – protocol, service, bytes, error rates.",
         "stats": [{"l": "train rows", "v": A["rows"]["train"]}, {"l": "test rows", "v": A["rows"]["test"]},
                   {"l": "features", "v": 41}]},
        {"id": 2, "title": "Audit", "nodes": ["audit"], "layer": 1,
         "en": f"Training has {A['n_attack_types']['train']} attack types, test has {A['n_attack_types']['test']}. "
               f"{unseen_types} types ({A['unseen_attack_rows_in_test']:,} test attacks) never appear in training. "
               f"U2R has only {u2r_train} training rows. Duplicate rows: {A['duplicate_rows']['train']}.",
         "hi": f"Training mein {A['n_attack_types']['train']} attack types hain, test mein {A['n_attack_types']['test']}. "
               f"{unseen_types} types ({A['unseen_attack_rows_in_test']:,} test attacks) training mein kabhi nahi aaye. "
               f"U2R ke sirf {u2r_train} training rows hain. Duplicate rows: {A['duplicate_rows']['train']}.",
         "stats": [{"l": "attack types train / test", "t": f"{A['n_attack_types']['train']} / {A['n_attack_types']['test']}"},
                   {"l": "unseen test attacks", "v": A["unseen_attack_rows_in_test"]},
                   {"l": "U2R training rows", "v": u2r_train}, {"l": "duplicates", "v": A["duplicate_rows"]["train"]}]},
        {"id": 3, "title": "Preprocess", "nodes": ["prep"], "layer": 2,
         "en": f"One-hot encode protocol, service and flag; log1p on skewed byte and count columns; drop the constant "
               f"column {', '.join(A['constant_columns'])}. Fitted on training data only – 41 raw columns become {n_feat_out} model inputs.",
         "hi": f"Protocol, service aur flag ko one-hot karte hain; byte/count columns par log1p; constant column "
               f"{', '.join(A['constant_columns'])} hata dete hain. Sirf training data par fit – 41 columns se {n_feat_out} inputs bante hain.",
         "stats": [{"l": "raw columns", "v": 41}, {"l": "model inputs", "v": n_feat_out},
                   {"l": "dropped", "v": len(A["constant_columns"])}]},
        {"id": 4, "title": "Train 4 models", "nodes": [f"m_{s}" for s in short.values()], "layer": 3, "sequential": True,
         "en": "Logistic Regression, Random Forest, XGBoost and LightGBM are trained on 85% of KDDTrain+ with class "
               "balancing; XGBoost and LightGBM get a 12-configuration random search. Numbers: validation macro-F1, binary · 5-class.",
         "hi": "Logistic Regression, Random Forest, XGBoost aur LightGBM ko KDDTrain+ ke 85% par train kiya, class balancing ke saath; "
               "XGBoost aur LightGBM ke liye 12-config random search. Numbers: validation macro-F1, binary · 5-class.",
         "stats": [{"l": f"{short[n]} binary F1", "v": val_b[n], "d": 4} for n in short]},
        {"id": 5, "title": "Select", "nodes": ["select"], "layer": 4,
         "en": f"{best_b} wins on validation macro-F1 for both tasks. Its configuration is re-checked with 5-fold CV on all of "
               f"KDDTrain+: {cv['binary']['mean']:.4f} ± {cv['binary']['std']:.4f} (binary), "
               f"{cv['multiclass']['mean']:.4f} ± {cv['multiclass']['std']:.4f} (5-class). Then it is refit on 100% of the training data.",
         "hi": f"Validation macro-F1 par {best_b} dono tasks mein jeeta. 5-fold CV se double-check: "
               f"{cv['binary']['mean']:.4f} ± {cv['binary']['std']:.4f} (binary), {cv['multiclass']['mean']:.4f} ± {cv['multiclass']['std']:.4f} (5-class). "
               f"Phir poore training data par refit.",
         "stats": [{"l": "CV macro-F1 binary", "v": cv["binary"]["mean"], "d": 4},
                   {"l": "CV macro-F1 5-class", "v": cv["multiclass"]["mean"], "d": 4}]},
        {"id": 6, "title": "Threshold gate", "nodes": ["gate"], "layer": 5, "chart": "slider",
         "en": f"P(attack) ≥ {thr:.2g} means attack. The threshold was chosen on validation only: maximise recall while keeping "
               f"false alarms ≤ 5%. Validation recall {pct(thr_info['val_recall'])}, validation false-alarm rate {pct(thr_info['val_false_alarm_rate'])}. "
               f"The slider shows what other thresholds would do on KDDTest+ – analysis only, never used for tuning.",
         "hi": f"P(attack) ≥ {thr:.2g} ho to attack. Threshold sirf validation par chuna: recall maximum rakho, false alarms 5% se kam. "
               f"Validation recall {pct(thr_info['val_recall'])}, false-alarm {pct(thr_info['val_false_alarm_rate'])}. "
               f"Slider dikhata hai doosre thresholds KDDTest+ par kya karte – sirf analysis, tuning nahi.",
         "stats": [{"l": "threshold on P(attack)", "t": f"{thr:.2g}"}, {"l": "val recall", "v": thr_info["val_recall"], "pct": True},
                   {"l": "val false alarms", "v": thr_info["val_false_alarm_rate"], "pct": True}]},
        {"id": 7, "title": "Live scoring", "nodes": [f"c_{c}" for c in CLASSES], "layer": 6, "live": True,
         "en": f"Each dot is one real KDDTest+ connection scored by the saved models. Grey until the gate; then teal = normal, "
               f"red = attack, amber ring = wrong class. The gate decides attack vs normal, the 5-class model names the family. "
               f"Click any dot for its details.",
         "hi": f"Har dot ek asli KDDTest+ connection hai jo saved models se score hua. Gate tak grey; phir teal = normal, "
               f"red = attack, amber ring = galat class. Gate attack/normal tay karta hai, 5-class model family batata hai. "
               f"Kisi bhi dot par click karke details dekho.",
         "stats": []},
        {"id": 8, "title": "Protocol A vs B", "nodes": ["eval"], "layer": 7, "chart": "ab",
         "en": f"Same-distribution validation accuracy {pct(acc_a)} vs {pct(dep_b['accuracy'])} on the official KDDTest+ "
               f"(recall {pct(dep_b['recall'])}, false alarms {pct(dep_b['false_alarm_rate'])}, ROC-AUC {dep_b['roc_auc']:.3f}). "
               f"The gap exists because KDDTest+ contains attack types and traffic mixes the model never trained on.",
         "hi": f"Same-distribution validation accuracy {pct(acc_a)}, lekin official KDDTest+ par {pct(dep_b['accuracy'])} "
               f"(recall {pct(dep_b['recall'])}, false alarms {pct(dep_b['false_alarm_rate'])}, AUC {dep_b['roc_auc']:.3f}). "
               f"Gap isliye hai kyunki KDDTest+ mein aise attack types hain jo model ne training mein kabhi nahi dekhe.",
         "stats": [{"l": "KDDTest+ recall", "v": dep_b["recall"], "pct": True},
                   {"l": "false alarms", "v": dep_b["false_alarm_rate"], "pct": True},
                   {"l": "ROC-AUC", "v": dep_b["roc_auc"], "d": 3}],
         "bars": [{"l": "A: validation", "v": acc_a}, {"l": "B: KDDTest+", "v": dep_b["accuracy"]}]},
        {"id": 9, "title": "Seen vs unseen", "nodes": ["eval"], "layer": 7, "chart": "bars",
         "en": f"Attack types seen in training: {pct(svu['seen']['recall'])} detected ({svu['seen']['detected']:,} of {svu['seen']['n']:,}). "
               f"The {unseen_types} never-seen types: {pct(svu['unseen']['recall'])} detected ({svu['unseen']['detected']:,} of {svu['unseen']['n']:,}). "
               f"The model never saw these attack types, yet catches most of them because they still look abnormal.",
         "hi": f"Training mein dekhe gaye attack types: {pct(svu['seen']['recall'])} pakde ({svu['seen']['detected']:,}/{svu['seen']['n']:,}). "
               f"Model ne ye {unseen_types} attack types kabhi nahi dekhe, phir bhi {pct(svu['unseen']['recall'], 0)} pakde "
               f"({svu['unseen']['detected']:,}/{svu['unseen']['n']:,}) – kyunki wo abhi bhi abnormal dikhte hain.",
         "stats": [{"l": "seen types detected", "v": svu["seen"]["recall"], "pct": True},
                   {"l": "unseen types detected", "v": svu["unseen"]["recall"], "pct": True}],
         "bars": [{"l": "seen in training", "v": svu["seen"]["recall"]}, {"l": "unseen", "v": svu["unseen"]["recall"], "c": "red"}]},
        {"id": 10, "title": "Per-class recall", "nodes": [f"c_{c}" for c in CLASSES], "layer": 6, "chart": "bars",
         "en": f"5-class recall on KDDTest+: " + ", ".join(f"{c} {pct(per_class[c], 0)}" for c in CLASSES) +
               f". R2L and U2R are the weak spot: only {A['class_distribution']['train'].get('R2L', 0):,} and {u2r_train} training rows, "
               f"and most of their test rows belong to unseen types.",
         "hi": f"KDDTest+ par 5-class recall: " + ", ".join(f"{c} {pct(per_class[c], 0)}" for c in CLASSES) +
               f". R2L aur U2R kamzor hain: sirf {A['class_distribution']['train'].get('R2L', 0):,} aur {u2r_train} training rows, "
               f"aur inke zyadatar test rows unseen types ke hain.",
         "stats": [{"l": "5-class accuracy", "v": dep_m["accuracy"], "pct": True},
                   {"l": "5-class macro-F1", "v": dep_m["f1_macro"], "d": 3}],
         "bars": [{"l": c, "v": per_class[c], "c": "red" if c in ("R2L", "U2R") else None} for c in CLASSES]},
        {"id": 11, "title": "Explain (SHAP)", "nodes": ["explain"], "layer": 8, "chart": "hbars",
         "en": f"SHAP values show which features drive each decision. Over {M['shap']['n_rows']:,} validation rows, "
               f"{top8[0]['feature']} matters most (mean |SHAP| {top8[0]['mean_abs_shap']:.2f}), then {top8[1]['feature']} and {top8[2]['feature']}. "
               f"Every scored dot carries its own top-3 reasons.",
         "hi": f"SHAP batata hai kaunse features decision chalate hain. {M['shap']['n_rows']:,} validation rows par "
               f"{top8[0]['feature']} sabse important hai (mean |SHAP| {top8[0]['mean_abs_shap']:.2f}), phir {top8[1]['feature']} aur {top8[2]['feature']}. "
               f"Har dot ke apne top-3 reasons hain.",
         "stats": [{"l": "rows explained", "v": M["shap"]["n_rows"]}, {"l": "#1 feature", "t": top8[0]["feature"]}],
         "bars": [{"l": f["feature"], "v": f["mean_abs_shap"]} for f in top8]},
        {"id": 12, "title": "Errors", "nodes": ["eval"], "layer": 7, "chart": "hbars",
         "en": "Most missed attacks: " + ", ".join(f"{m['attack']} ({m['binary_missed']:,} of {m['n']:,})" for m in missed) +
               f". The binary gate called them normal and the 5-class model mostly predicts "
               f"{mc_pred.get(missed[0]['attack'], '?')} for {missed[0]['attack']}: these password-guessing and SNMP attacks "
               f"look like ordinary logins at the connection-feature level.",
         "hi": "Sabse zyada miss hue attacks: " + ", ".join(f"{m['attack']} ({m['binary_missed']:,}/{m['n']:,})" for m in missed) +
               f". Gate ne inhe normal bola aur 5-class model {missed[0]['attack']} ko zyadatar {mc_pred.get(missed[0]['attack'], '?')} "
               f"predict karta hai: password-guessing aur SNMP attacks connection features mein normal login jaise dikhte hain.",
         "stats": [{"l": "attacks missed", "v": M["error_analysis"]["binary_total_missed_attacks"]},
                   {"l": "false alarms", "v": M["error_analysis"]["binary_false_alarms"]}],
         "bars": [{"l": m["attack"], "v": m["binary_miss_rate"], "c": "red", "n": f"{m['binary_missed']:,}/{m['n']:,}"} for m in missed]},
        {"id": 13, "title": "Limitations & next steps", "nodes": [], "layer": 9,
         "en": "NSL-KDD traffic is from 1998/99, so these numbers measure the method, not a modern network. Next: add an "
               "anomaly detector for zero-day attacks, oversample or re-weight R2L/U2R, and validate on newer datasets such as CIC-IDS2017.",
         "hi": "NSL-KDD ka traffic 1998/99 ka hai, isliye ye numbers method ko naapte hain, modern network ko nahi. Aage: zero-day "
               "attacks ke liye anomaly detector, R2L/U2R ke liye oversampling, aur CIC-IDS2017 jaise naye datasets par validation.",
         "stats": [{"l": "inference per connection (µs)", "v": dep_b["inference_us_per_row"], "d": 1},
                   {"l": "model size (MB)", "v": M["deployed"]["binary"]["size_mb"], "d": 2}]},
    ]

    data = {
        "classes": CLASSES, "threshold": thr, "best": M["best"], "best_short": short[best_b], "nodes": nodes, "steps": steps,
        "sensitivity": sens, "rows": records, "models": list(short.values()),
        "generated_from": ["reports/metrics.json", "reports/audit.json", "reports/train_summary.json",
                           "models/binary_model.joblib", "models/multiclass_model.joblib", "data/KDDTest+.txt"],
    }
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")  # never close the <script>
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", blob)
    OUT.write_text(html, encoding="utf-8")
    n_attack = sum(r["true"] != "Normal" for r in records)
    print(f"Scored {N_ROWS} KDDTest+ rows ({n_attack} attacks), SHAP for {N_SHAP}. "
          f"Workflow simulation written to {OUT} ({OUT.stat().st_size / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
