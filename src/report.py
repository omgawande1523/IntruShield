"""IntruShield - build the self-contained HTML evaluation report from metrics.json + audit.json."""
import base64
import json
from datetime import datetime

from config import CLASSES, FIG_DIR, REPORTS_DIR

MODEL_ORDER = ["LogisticRegression", "RandomForest", "XGBoost", "LightGBM"]
CSS = """
:root{--navy:#0b2545;--teal:#13a4a4;--ink:#1f2933;--muted:#5f6b7a;--bg:#f6f8fa;--card:#fff;--line:#e3e8ee}
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Inter,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.55}
header{background:linear-gradient(120deg,var(--navy),#123a6b 70%,var(--teal));color:#fff;padding:40px 48px}
header h1{margin:0;font-size:34px;letter-spacing:.5px}header p{margin:8px 0 0;opacity:.9;font-size:16px}
nav{position:sticky;top:0;background:var(--navy);padding:8px 48px;z-index:9;overflow-x:auto;white-space:nowrap}
nav a{color:#cfe8e8;text-decoration:none;margin-right:18px;font-size:13px}nav a:hover{color:#fff}
main{max-width:1180px;margin:0 auto;padding:24px 32px 60px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:26px 30px;margin:22px 0;box-shadow:0 1px 3px rgba(11,37,69,.06)}
h2{margin:0 0 14px;color:var(--navy);font-size:22px;border-left:5px solid var(--teal);padding-left:12px}
h3{color:var(--navy);margin:20px 0 8px;font-size:16px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}
th{background:var(--navy);color:#fff;text-align:left;padding:8px 10px;font-weight:600}
td{padding:7px 10px;border-bottom:1px solid var(--line)}tr:nth-child(even) td{background:#f9fbfc}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.best td{font-weight:700;background:#e8f6f6!important}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin:12px 0 4px}
.kpi{background:linear-gradient(160deg,#f2fafa,#fff);border:1px solid #cfe8e8;border-radius:10px;padding:14px 16px}
.kpi .v{font-size:26px;font-weight:700;color:var(--navy)}.kpi .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
figure{margin:18px 0;text-align:center}figure img{max-width:100%;border:1px solid var(--line);border-radius:6px}
figcaption{font-size:12.5px;color:var(--muted);margin-top:6px}
.note{background:#fff8e6;border-left:4px solid #e0a800;padding:10px 14px;border-radius:6px;font-size:14px}
.ok{background:#eaf7f1;border-left:4px solid #2e9e6b;padding:10px 14px;border-radius:6px;font-size:14px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:800px){.cols{grid-template-columns:1fr}}
code{background:#eef2f6;padding:1px 5px;border-radius:4px;font-size:12.5px}
footer{text-align:center;color:var(--muted);font-size:12px;padding:20px}
"""


def img(name, caption):
    data = base64.b64encode((FIG_DIR / name).read_bytes()).decode()
    return f'<figure><img src="data:image/png;base64,{data}" alt="{caption}"><figcaption>{caption}</figcaption></figure>'


def pct(x, d=2):
    return f"{100 * x:.{d}f}%"


def f4(x):
    return f"{x:.4f}"


def table(headers, rows, best_row=None, num_from=1):
    h = "".join(f'<th{" class=num" if i >= num_from else ""}>{x}</th>' for i, x in enumerate(headers))
    body = ""
    for r_i, r in enumerate(rows):
        cls = ' class="best"' if best_row is not None and r_i == best_row else ""
        body += f"<tr{cls}>" + "".join(
            f'<td{" class=num" if i >= num_from else ""}>{x}</td>' for i, x in enumerate(r)) + "</tr>"
    return f"<table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"


def main():
    M = json.loads((REPORTS_DIR / "metrics.json").read_text())
    A = json.loads((REPORTS_DIR / "audit.json").read_text())
    P = M["protocols"]
    best_b, best_m = M["best"]["binary"], M["best"]["multiclass"]
    dep_b, dep_m = M["deployed"]["binary"]["B: KDDTest+"], M["deployed"]["multiclass"]["B: KDDTest+"]
    dep_b21 = M["deployed"]["binary"]["B: KDDTest-21"]
    thr = M["threshold"]
    svu = M["seen_vs_unseen"]
    unseen_rows = A["unseen_attack_rows_in_test"]
    unseen_types = list(A["attacks_in_test_not_in_train"].keys())
    total_test_attacks = A["binary_distribution"]["test"]["attack"]

    def model_table(task):
        rows, best_i = [], None
        for i, n in enumerate(MODEL_ORDER):
            a, b, b21 = P["A: validation"][task][n], P["B: KDDTest+"][task][n], P["B: KDDTest-21"][task][n]
            meta = M["model_meta"][task][n]
            if n == M["best"][task]:
                best_i = i
            rows.append([n, f4(a["f1_macro"]), f4(b["f1_macro"]), f4(b21["f1_macro"]),
                         pct(a["accuracy"]), pct(b["accuracy"]), pct(a["recall"]), pct(b["recall"]),
                         pct(a["false_alarm_rate"]), pct(b["false_alarm_rate"]),
                         f4(a["roc_auc"]), f4(b["roc_auc"]),
                         f"{meta['train_time_s']:.1f}", f"{meta['inference_us_per_row']:.1f}", f"{meta['size_mb']:.2f}"])
        return table(["Model", "F1m A", "F1m B", "F1m B-21", "Acc A", "Acc B", "Recall A", "Recall B",
                      "FAR A", "FAR B", "AUC A", "AUC B", "Train s", "Infer µs/row", "Size MB"], rows, best_i)

    def full_metric_table(task, dname):
        rows = []
        for n in MODEL_ORDER:
            m = P[dname][task][n]
            rows.append([n, pct(m["accuracy"]), f4(m["precision"]), f4(m["recall"]), f4(m["f1_macro"]),
                         f4(m["f1_weighted"]), f4(m["roc_auc"]), pct(m["false_alarm_rate"])])
        return table(["Model", "Accuracy", "Precision", "Recall (DR)", "F1 macro", "F1 weighted", "ROC-AUC",
                      "False alarm"], rows, MODEL_ORDER.index(M["best"][task]))

    # ---- sections --------------------------------------------------------------------------
    kpis = f"""
<div class="kpis">
<div class="kpi"><div class="v">{pct(dep_b['recall'], 1)}</div><div class="l">Attack detection rate · KDDTest+</div></div>
<div class="kpi"><div class="v">{pct(dep_b['false_alarm_rate'], 1)}</div><div class="l">False-alarm rate · KDDTest+</div></div>
<div class="kpi"><div class="v">{f4(dep_b['roc_auc'])}</div><div class="l">ROC-AUC (binary) · KDDTest+</div></div>
<div class="kpi"><div class="v">{f4(dep_m['f1_macro'])}</div><div class="l">Macro-F1 (5-class) · KDDTest+</div></div>
<div class="kpi"><div class="v">{f4(P['A: validation']['binary'][best_b]['f1_macro'])}</div><div class="l">Macro-F1 (binary) · validation</div></div>
<div class="kpi"><div class="v">{M['model_meta']['binary'][best_b]['inference_us_per_row']:.0f} µs</div><div class="l">Inference per connection</div></div>
</div>"""

    dist = lambda d: ", ".join(f"{k}: {v:,}" for k, v in d.items())  # noqa: E731
    unseen_tbl = table(["Attack type (test only)", "Class", "Rows in KDDTest+"],
                       [[k, v["class"], f"{v['test_rows']:,}"] for k, v in
                        sorted(A["attacks_in_test_not_in_train"].items(), key=lambda kv: -kv[1]["test_rows"])], num_from=2)

    audit_sec = f"""
<p>NSL-KDD is the de-duplicated revision of KDD'99. Each row is one TCP/UDP/ICMP connection described by
41 features (9 basic, 13 content, 9 time-based traffic, 10 host-based traffic) plus an attack label and a
difficulty score (dropped from the feature set, kept for analysis).</p>
{table(["", "KDDTrain+", "KDDTest+", "KDDTest-21"], [
    ["Rows", f"{A['rows']['train']:,}", f"{A['rows']['test']:,}", f"{A['rows']['test21']:,}"],
    ["Exact duplicate rows", str(A['duplicate_rows']['train']), str(A['duplicate_rows']['test']), "-"],
    ["Test rows whose feature vector appears in train", "-", str(A['duplicate_rows']['test_rows_also_in_train']), "-"],
    ["Distinct attack types", str(A['n_attack_types']['train']), str(A['n_attack_types']['test']), "-"],
    ["5-class distribution", dist(A['class_distribution']['train']), dist(A['class_distribution']['test']), dist(A['class_distribution']['test21'])],
    ["Binary distribution", dist(A['binary_distribution']['train']), dist(A['binary_distribution']['test']), "-"],
    ["Constant columns (dropped)", ", ".join(A['constant_columns']) or "none", "", ""],
])}
<h3>Attack types present in KDDTest+ but absent from KDDTrain+</h3>
<p>{len(unseen_types)} attack types, <b>{unseen_rows:,} rows ({pct(unseen_rows / total_test_attacks, 1)} of all test attacks)</b>,
never appear in training. This is the designed difficulty of NSL-KDD and the main driver of the Protocol A → B gap.</p>
{unseen_tbl}"""

    prep_sec = f"""
<p>A single scikit-learn <code>Pipeline</code> (<code>ColumnTransformer</code> → classifier) is fitted on training
rows only, and persisted together with the model, so test rows always pass through exactly the training-time
transformation.</p>
<ul>
<li><b>Categorical</b> (<code>protocol_type</code>, <code>service</code>, <code>flag</code>): <code>OneHotEncoder(handle_unknown="ignore")</code> – services seen only in test become all-zero rather than crashing.</li>
<li><b>Heavily skewed counts/bytes</b> (duration, src_bytes, dst_bytes, hot, count, srv_count, dst_host_count, …): <code>log1p</code>.</li>
<li><b>Scaling</b>: <code>StandardScaler</code> on all numeric columns for LogisticRegression only; trees use raw (log-transformed) values.</li>
<li><b>Dropped</b>: constant column(s) {', '.join(A['constant_columns'])}; the difficulty score.</li>
<li><b>Imbalance</b>: <code>class_weight="balanced"</code> (LR, LightGBM), <code>balanced_subsample</code> (RandomForest), balanced <code>sample_weight</code> (XGBoost).</li>
</ul>
<p><b>Leakage discipline:</b> KDDTrain+ was split 85/15 stratified on the 5-class label
({M['split']['train_rows']:,} / {M['split']['val_rows']:,} rows, <code>random_state=42</code>). Hyper-parameter search
(RandomizedSearchCV, 12 configurations × 3-fold, macro-F1) ran on the 85 % part, model selection and the decision
threshold used only the 15 % validation part. KDDTest+ / KDDTest-21 were loaded for the first time in
<code>evaluate.py</code>.</p>"""

    def params(task, n):
        p = M["model_meta"][task][n]["best_params"]
        return ", ".join(f"{k}={v:.3g}" if isinstance(v, float) else f"{k}={v}" for k, v in p.items()) or "defaults"

    models_sec = f"""
{table(["Model", "Role", "Imbalance handling", "Tuned params (binary)", "Tuned params (multiclass)"], [
    ["LogisticRegression", "linear baseline", "class_weight=balanced", "C=1 (not tuned)", "C=1 (not tuned)"],
    ["RandomForest", "bagging, 200 trees", "class_weight=balanced_subsample", "not tuned", "not tuned"],
    ["XGBoost", "gradient boosting (hist)", "balanced sample_weight", params("binary", "XGBoost"), params("multiclass", "XGBoost")],
    ["LightGBM", "gradient boosting (leaf-wise)", "class_weight=balanced", params("binary", "LightGBM"), params("multiclass", "LightGBM")],
], num_from=99)}
<p>Selected by validation macro-F1: <b>{best_b}</b> for the binary task and <b>{best_m}</b> for the 5-class task.
5-fold stratified CV of the selected configuration on the whole of KDDTrain+:
binary macro-F1 <b>{M['cv5']['binary']['mean']:.4f} ± {M['cv5']['binary']['std']:.4f}</b>,
multiclass macro-F1 <b>{M['cv5']['multiclass']['mean']:.4f} ± {M['cv5']['multiclass']['std']:.4f}</b>.</p>"""

    leak = M["leakage_check"]
    leak_html = (f'<div class="note"><b>Leakage check triggered</b> (max Protocol A accuracy {pct(leak["max_protocol_a_accuracy"])} &gt; 99.9 %). '
                 f'{leak["val_rows_with_identical_feature_vector_in_train_split"]} of {leak["val_rows"]:,} validation rows have a feature vector '
                 f'identical to a training-split row; KDDTrain+ contains {leak["exact_duplicate_rows_in_kddtrain"]} exact duplicate rows. '
                 f'The near-perfect in-distribution score therefore is not explained by duplicate leakage.</div>'
                 if leak["triggered"] else f'<div class="ok">Max Protocol A accuracy {pct(leak["max_protocol_a_accuracy"])} ≤ 99.9 %; leakage check not triggered.</div>')

    results_sec = f"""
<p><b>Protocol A</b> = the 15 % stratified hold-out of KDDTrain+ (same distribution as training).
<b>Protocol B</b> = the official KDDTest+ (and its hard subset KDDTest-21, which removes every record that 21 KDD'99
learners all classified correctly). Binary metrics use each model's own validation-chosen threshold; FAR = share of
normal connections flagged as attacks.</p>
<h3>Binary (normal vs attack)</h3>{model_table("binary")}
<h3>Multiclass (Normal / DoS / Probe / R2L / U2R)</h3>{model_table("multiclass")}
{leak_html}
{img(M['figures']['model_comparison'], "Macro-F1 of every model under Protocol A (validation), Protocol B (KDDTest+) and KDDTest-21.")}
<h3>Full metric set – Protocol B, KDDTest+</h3>
<div class="cols"><div><h3>Binary</h3>{full_metric_table("binary", "B: KDDTest+")}</div>
<div><h3>Multiclass</h3>{full_metric_table("multiclass", "B: KDDTest+")}</div></div>
<h3>Deployed models (refit on 100 % of KDDTrain+)</h3>
{table(["Model", "Dataset", "Accuracy", "Precision", "Recall", "F1 macro", "ROC-AUC", "False alarm"], [
    [f"{best_b} (binary)", "KDDTest+", pct(dep_b['accuracy']), f4(dep_b['precision']), f4(dep_b['recall']), f4(dep_b['f1_macro']), f4(dep_b['roc_auc']), pct(dep_b['false_alarm_rate'])],
    [f"{best_b} (binary)", "KDDTest-21", pct(dep_b21['accuracy']), f4(dep_b21['precision']), f4(dep_b21['recall']), f4(dep_b21['f1_macro']), f4(dep_b21['roc_auc']), pct(dep_b21['false_alarm_rate'])],
    [f"{best_m} (5-class)", "KDDTest+", pct(dep_m['accuracy']), f4(dep_m['precision']), f4(dep_m['recall']), f4(dep_m['f1_macro']), f4(dep_m['roc_auc']), pct(dep_m['false_alarm_rate'])],
], num_from=2)}
{img(M['figures']['roc_pr_curves'], "ROC (left, x-axis zoomed for validation) and Precision-Recall (right) curves of all binary models on validation (top) and KDDTest+ (bottom).")}"""

    gap_a = P["A: validation"]["binary"][best_b]["f1_macro"]
    gap_b = P["B: KDDTest+"]["binary"][best_b]["f1_macro"]
    s, u = svu[best_b]["seen"], svu[best_b]["unseen"]
    gap_sec = f"""
<p>For {best_b} the binary macro-F1 drops from <b>{f4(gap_a)}</b> (Protocol A) to <b>{f4(gap_b)}</b> (KDDTest+).
Splitting KDDTest+ attacks by whether their attack type ever occurred in KDDTrain+ explains the drop:</p>
{table(["Model", "Seen types: n", "Seen: detected", "Seen: recall", "Unseen types: n", "Unseen: detected", "Unseen: recall"], [
    [n, f"{svu[n]['seen']['n']:,}", f"{svu[n]['seen']['detected']:,}", pct(svu[n]['seen']['recall'], 1),
     f"{svu[n]['unseen']['n']:,}", f"{svu[n]['unseen']['detected']:,}", pct(svu[n]['unseen']['recall'], 1)] for n in MODEL_ORDER], MODEL_ORDER.index(best_b))}
<p>{best_b} detects <b>{pct(s['recall'], 1)}</b> of attacks whose type it has seen but only <b>{pct(u['recall'], 1)}</b> of the
{u['n']:,} connections belonging to the {len(unseen_types)} unseen types. In addition, several <i>seen</i> R2L types
(e.g. guess_passwd, warezmaster) appear in test with far higher frequency and different feature profiles than in
training, and many R2L/U2R connections are content-level attacks that look like normal logins at the connection-feature
level. Nothing in this gap is a bug: it is the covariate and label shift NSL-KDD was built to expose, and it is the
honest number to quote for deployment.</p>
{img(M['figures']['seen_vs_unseen'], "Detection rate on KDDTest+ attacks, split by whether the attack type occurs in KDDTrain+ (binary task, validation-chosen thresholds).")}
{img(M['figures']['per_attack_detection'], "Detection rate per attack type on KDDTest+ (types with at least 5 rows).")}"""

    pcr_rows = []
    for c in CLASSES:
        pcr_rows.append([c, f"{A['class_distribution']['train'].get(c, 0):,}", f"{A['class_distribution']['test'].get(c, 0):,}",
                         f4(P["A: validation"]["multiclass"][best_m]["per_class_recall"][c]),
                         f4(P["B: KDDTest+"]["multiclass"][best_m]["per_class_recall"][c]),
                         f4(P["B: KDDTest+"]["multiclass"][best_m]["per_class_f1"][c])])
    perclass_sec = f"""
{table(["Class", "Train rows", "Test rows", "Recall A (val)", "Recall B (KDDTest+)", "F1 B (KDDTest+)"], pcr_rows)}
<p>DoS and Probe transfer well. R2L and U2R are rare in training ({A['class_distribution']['train'].get('R2L', 0):,} and
{A['class_distribution']['train'].get('U2R', 0):,} rows) but much more frequent in test
({A['class_distribution']['test'].get('R2L', 0):,} and {A['class_distribution']['test'].get('U2R', 0):,}), and most of their
test rows are of unseen types – they are the weak spot of every model.</p>
{img(M['figures']['per_class_recall'], f"Per-class recall of {best_m} under both protocols; the rare R2L/U2R classes are highlighted.")}
{img(M['figures']['confusion_multiclass'], f"Confusion matrices of the deployed {best_m} 5-class model on KDDTest+ (counts and row-normalised).")}
{img(M['figures']['confusion_binary'], f"Confusion matrices of the deployed {best_b} binary model on KDDTest+ at threshold {thr['value']:.3f}.")}"""

    shap_sec = f"""
<p>TreeExplainer SHAP values of the <b>{M['shap']['model']}</b> binary model on {M['shap']['n_rows']:,} random validation rows
(computed in {M['shap']['time_s']:.1f} s). Each value is the feature's contribution to the log-odds of "attack".</p>
{table(["Rank", "Feature", "mean |SHAP|"], [[i + 1, r["feature"], f"{r['mean_abs_shap']:.4f}"] for i, r in enumerate(M["shap"]["top15"])], num_from=2)}
<div class="cols">{img(M['figures']['shap_summary'], "SHAP beeswarm: each dot is one connection; colour is the (preprocessed) feature value.")}
{img(M['figures']['feature_importance'], "Top 15 features by mean absolute SHAP value.")}</div>"""

    sens_tbl = table(["Operating point", "Threshold", "Val recall", "Val FAR", "KDDTest+ recall", "KDDTest+ FAR", "KDDTest+ F1 macro"],
                     [[r["label"], f"{r['threshold']:.3g}", pct(r["val_recall"]), pct(r["val_far"]), pct(r["test_recall"]),
                       pct(r["test_far"]), f4(r["test_f1_macro"])] for r in M["threshold_sensitivity"]], 0)
    thr_sec = f"""
<p>The operating point was chosen on the validation split only: <b>maximise attack recall subject to a false-alarm
rate ≤ {pct(thr['max_far_constraint'], 0)}</b>. Recall can only fall as the threshold rises, so the optimum is the lowest
threshold whose validation FAR still respects the budget. Because the validation split is almost perfectly separable,
this rule spends the whole false-alarm budget on sensitivity – deliberately, since the detector must face attack types
that never occur in validation. Result: threshold <b>{thr['value']:.3g}</b> on P(attack) → validation recall
<b>{pct(thr['val_recall'])}</b>, validation false-alarm rate <b>{pct(thr['val_false_alarm_rate'])}</b>. On KDDTest+ the
same threshold gives recall <b>{pct(dep_b['recall'])}</b> and false-alarm rate <b>{pct(dep_b['false_alarm_rate'])}</b>
({M['error_analysis']['binary_false_alarms']:,} of {A['binary_distribution']['test']['normal']:,} normal connections flagged).</p>
{img(M['figures']['threshold_curve'], "Recall and false-alarm rate as a function of the decision threshold on the validation split (log-scale threshold).")}
<h3>Threshold sensitivity (analysis only – the deployed threshold was fixed before KDDTest+ was read)</h3>
{sens_tbl}
<p>Validation cannot distinguish thresholds between 10<sup>-6</sup> and 0.5 (recall and FAR barely move), whereas on
KDDTest+ the choice moves recall by tens of points: unseen attacks receive low but non-zero attack probabilities, so a
sensitive threshold catches many of them at the cost of a higher false-alarm rate under distribution shift.</p>"""

    ea = M["error_analysis"]
    err_sec = f"""
<p>Deployed models on KDDTest+: <b>{ea['binary_total_missed_attacks']:,}</b> of {total_test_attacks:,} attacks missed by the binary model,
<b>{ea['binary_false_alarms']:,}</b> false alarms.</p>
<h3>Attack types most often missed (binary)</h3>
{table(["Attack", "Class", "Test rows", "Missed", "Miss rate", "Seen in train"],
       [[r["attack"], r["class"], f"{r['n']:,}", f"{r['binary_missed']:,}", pct(r["binary_miss_rate"], 1), "yes" if r["seen_in_train"] else "<b>no</b>"] for r in ea["most_missed_binary"]], num_from=2)}
<h3>Attack types most often mis-classified (5-class)</h3>
{table(["Attack", "True class", "Test rows", "Wrong", "Error rate", "Most common prediction", "Seen in train"],
       [[r["attack"], r["class"], f"{r['n']:,}", f"{r['multiclass_wrong']:,}", pct(r["multiclass_error_rate"], 1), r["multiclass_most_common_prediction"], "yes" if r["seen_in_train"] else "<b>no</b>"] for r in ea["most_misclassified_multiclass"]], num_from=2)}"""

    limits_sec = """
<ul>
<li><b>Dataset age and realism.</b> NSL-KDD derives from 1998/99 DARPA traffic; services, attack tooling and traffic mixes have changed. Numbers here measure method quality, not expected performance on a modern network.</li>
<li><b>Unseen attacks.</b> Supervised classifiers can only generalise from feature similarity; zero-day detection needs anomaly / novelty detection (e.g. isolation forest or autoencoder on normal traffic) alongside the classifier.</li>
<li><b>R2L / U2R.</b> With few hundred training rows and strong distribution shift, per-class recall is low. Options: targeted oversampling or focal loss, hierarchical models (attack → family), or cost-sensitive thresholds per class.</li>
<li><b>Thresholding.</b> The threshold maximises recall under a 5 % validation FAR; because validation is in-distribution, the test FAR differs. Calibrating on a small labelled sample of target traffic would tighten this.</li>
<li><b>Tuning budget.</b> 12 random configurations × 3 folds per booster to stay within the 25-minute CPU budget; a larger search or early-stopping tuning may add a little macro-F1 on Protocol A but is unlikely to close the Protocol B gap.</li>
<li><b>Next steps.</b> Evaluate on CIC-IDS2017 / UNSW-NB15, add an anomaly-score channel, estimate calibration (Brier / reliability), and package the pipeline as a streaming scorer with drift monitoring on the top SHAP features.</li>
</ul>"""

    sections = [
        ("problem", "1. Problem", f"""<p><b>IntruShield</b> is a network intrusion detection model that classifies individual connection records as
<i>normal</i> or <i>attack</i> (binary task) and assigns attacks to one of four families – DoS, Probe, R2L, U2R
(5-class task). Operational priorities: high detection rate, a bounded false-alarm rate (≤ 5 % on normal traffic), and
honest measurement of how performance degrades on attack types never seen in training.</p>{kpis}"""),
        ("data", "2. Dataset &amp; Audit", audit_sec),
        ("prep", "3. Preprocessing", prep_sec),
        ("models", "4. Models Compared", models_sec),
        ("results", "5. Results – Protocol A vs Protocol B", results_sec),
        ("gap", "6. Why the gap exists – unseen attacks", gap_sec),
        ("perclass", "7. Per-class Performance", perclass_sec),
        ("shap", "8. Explainability (SHAP)", shap_sec),
        ("threshold", "9. Threshold &amp; False Alarms", thr_sec),
        ("errors", "10. Error Analysis", err_sec),
        ("limits", "11. Limitations &amp; Next Steps", limits_sec),
    ]
    nav = "".join(f'<a href="#{i}">{t.split(". ", 1)[1].replace("&amp;", "&")}</a>' for i, t, _ in sections)
    body = "".join(f'<section id="{i}"><h2>{t}</h2>{h}</section>' for i, t, h in sections)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IntruShield – NSL-KDD Intrusion Detection Evaluation</title><style>{CSS}</style></head><body>
<header><h1>IntruShield · Network Intrusion Detection on NSL-KDD</h1>
<p>Evaluation report · generated {datetime.now():%Y-%m-%d %H:%M} · binary model: {best_b} · 5-class model: {best_m} · random_state=42</p></header>
<nav>{nav}</nav><main>{body}</main>
<footer>All figures and numbers in this report are produced by the IntruShield pipeline (src/data.py → train.py → evaluate.py → report.py). No external benchmarks are quoted.</footer>
</body></html>"""
    out = REPORTS_DIR / "eval_report.html"
    out.write_text(html, encoding="utf-8")
    print(f"Report written to {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
