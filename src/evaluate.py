"""IntruShield - evaluation under Protocol A (validation split) and Protocol B (KDDTest+/-21).

Produces reports/metrics.json and all figures in reports/figures/.
"""
import io
import json
import time
import warnings

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402
import shap  # noqa: E402
from sklearn.metrics import (accuracy_score, auc, confusion_matrix, f1_score,  # noqa: E402
                             precision_recall_curve, precision_score, recall_score,
                             roc_auc_score, roc_curve)

from config import (CANDIDATES_DIR, CLASSES, FEATURES, FIG_DIR, MODELS_DIR, NAVY, PALETTE,  # noqa: E402
                    RANDOM_STATE, REPORTS_DIR, TEAL)
from data import load_split  # noqa: E402

warnings.filterwarnings("ignore")
sns.set_theme(style="whitegrid", context="talk", font_scale=0.75)
plt.rcParams.update({"axes.edgecolor": "#cccccc", "grid.color": "#e6e6e6", "axes.titleweight": "bold",
                     "axes.titlecolor": NAVY, "figure.dpi": 110})
MODEL_ORDER = ["LogisticRegression", "RandomForest", "XGBoost", "LightGBM"]
MODEL_COLOR = dict(zip(MODEL_ORDER, PALETTE))
PROTO_COLOR = {"A: validation": PALETTE[0], "B: KDDTest+": PALETTE[1], "B: KDDTest-21": PALETTE[2]}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, bbox_inches="tight")
    plt.close(fig)
    return name


def binary_metrics(y, p, thr):
    pred = (p >= thr).astype(int)
    return {
        "accuracy": accuracy_score(y, pred), "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred), "f1_macro": f1_score(y, pred, average="macro"),
        "f1_weighted": f1_score(y, pred, average="weighted"), "roc_auc": roc_auc_score(y, p),
        "false_alarm_rate": float(pred[y == 0].mean()), "threshold": thr,
        "confusion": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
    }


def multiclass_metrics(y, proba):
    pred = proba.argmax(1)
    labels = list(range(len(CLASSES)))
    present = sorted(set(y))
    try:
        roc = roc_auc_score(y, proba[:, present] / proba[:, present].sum(1, keepdims=True),
                            multi_class="ovr", average="macro", labels=present)
    except ValueError:
        roc = float("nan")
    rec_per_class = recall_score(y, pred, labels=labels, average=None, zero_division=0)
    normal = CLASSES.index("Normal")
    return {
        "accuracy": accuracy_score(y, pred),
        "precision": precision_score(y, pred, average="macro", zero_division=0),
        "recall": recall_score(y, pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y, pred, average="macro"), "f1_weighted": f1_score(y, pred, average="weighted"),
        "roc_auc": float(roc), "false_alarm_rate": float((pred[y == normal] != normal).mean()),
        "per_class_recall": dict(zip(CLASSES, map(float, rec_per_class))),
        "per_class_f1": dict(zip(CLASSES, map(float, f1_score(y, pred, labels=labels, average=None,
                                                                 zero_division=0)))),
        "confusion": confusion_matrix(y, pred, labels=labels).tolist(),
    }


def model_size_mb(obj):
    buf = io.BytesIO()
    joblib.dump(obj, buf)
    return buf.getbuffer().nbytes / 1e6


def timed_proba(pipe, X):
    t0 = time.perf_counter()
    p = pipe.predict_proba(X)
    return p, (time.perf_counter() - t0) / len(X) * 1e6


def main():
    t_start = time.perf_counter()
    summary = json.loads((REPORTS_DIR / "train_summary.json").read_text())
    audit = json.loads((REPORTS_DIR / "audit.json").read_text())
    train, test, test21 = load_split("train"), load_split("test"), load_split("test21")
    val = train.iloc[np.load(MODELS_DIR / "val_idx.npy")]
    bundles = {t: joblib.load(MODELS_DIR / f"{t}_model.joblib") for t in ("binary", "multiclass")}
    le = bundles["multiclass"]["label_encoder"]
    best = {t: summary["tasks"][t]["best_model"] for t in bundles}
    thresholds = summary["tasks"]["binary"]["candidate_thresholds"]
    seen_attacks = set(train["attack"])
    datasets = {"A: validation": val, "B: KDDTest+": test, "B: KDDTest-21": test21}

    metrics = {"best": best, "protocols": {k: {"binary": {}, "multiclass": {}} for k in datasets},
               "model_meta": {"binary": {}, "multiclass": {}}, "deployed": {},
               "cv5": {t: summary["tasks"][t]["cv5_f1_macro"] for t in bundles},
               "threshold": {k: v for k, v in summary["tasks"]["binary"]["threshold"].items()
                             if k != "curve"},
               "split": summary["split"]}
    probas = {"binary": {}, "multiclass": {}}  # (model, dataset) -> proba on that dataset

    # ---- every candidate model, both protocols ----------------------------------------------
    for task in ("binary", "multiclass"):
        for name in MODEL_ORDER:
            pipe = joblib.load(CANDIDATES_DIR / f"{task}_{name}.joblib")
            meta = {"train_time_s": summary["tasks"][task]["models"][name]["train_time_s"],
                    "size_mb": model_size_mb(pipe),
                    "best_params": summary["tasks"][task]["models"][name]["best_params"]}
            for dname, df in datasets.items():
                X = df[FEATURES]
                p, us = timed_proba(pipe, X)
                probas[task][(name, dname)] = p
                if task == "binary":
                    m = binary_metrics(df["is_attack"].values, p[:, 1], thresholds[name])
                else:
                    m = multiclass_metrics(le.transform(df["label5"]), p)
                m["inference_us_per_row"] = us
                metrics["protocols"][dname][task][name] = m
                if dname == "B: KDDTest+":
                    meta["inference_us_per_row"] = us
            metrics["model_meta"][task][name] = meta
            print(f"[{task}] {name}: " + "  ".join(
                f"{d.split(':')[1].strip()} F1m={metrics['protocols'][d][task][name]['f1_macro']:.4f}"
                for d in datasets), flush=True)

    # ---- deployed models (refit on 100% of KDDTrain+) on Protocol B -------------------------
    for task, b in bundles.items():
        metrics["deployed"][task] = {"model": b["model_name"], "refit_time_s": b["refit_time_s"],
                                     "size_mb": model_size_mb(b["pipeline"])}
        for dname in ("B: KDDTest+", "B: KDDTest-21"):
            df = datasets[dname]
            p, us = timed_proba(b["pipeline"], df[FEATURES])
            probas[task][("deployed", dname)] = p
            m = (binary_metrics(df["is_attack"].values, p[:, 1], b["threshold"]) if task == "binary"
                 else multiclass_metrics(le.transform(df["label5"]), p))
            m["inference_us_per_row"] = us
            metrics["deployed"][task][dname] = m

    # ---- leakage check -------------------------------------------------------------------------
    max_acc_a = max(m["accuracy"] for t in ("binary", "multiclass")
                    for m in metrics["protocols"]["A: validation"][t].values())
    metrics["leakage_check"] = {
        "max_protocol_a_accuracy": max_acc_a, "triggered": bool(max_acc_a > 0.999),
        "val_rows_with_identical_feature_vector_in_train_split": summary["split"]["val_rows_duplicated_in_train"],
        "val_rows": summary["split"]["val_rows"],
        "exact_duplicate_rows_in_kddtrain": audit["duplicate_rows"]["train"],
        "note": ("Protocol A accuracy > 99.9%: checked duplicates between train and validation "
                 "splits; see counts. NSL-KDD was de-duplicated by its authors, so near-perfect "
                 "same-distribution accuracy reflects an easy in-distribution task, not leakage."
                 if max_acc_a > 0.999 else "Protocol A accuracy <= 99.9%; no leakage check needed."),
    }

    # ---- seen vs unseen attacks on KDDTest+ (binary detection rate) --------------------------
    test_attack = test[test["is_attack"] == 1].copy()
    test_attack["seen"] = test_attack["attack"].isin(seen_attacks)
    svu = {}
    for name in MODEL_ORDER + ["deployed"]:
        p = probas["binary"][(name, "B: KDDTest+")][:, 1][test["is_attack"].values == 1]
        thr = bundles["binary"]["threshold"] if name == "deployed" else thresholds[name]
        det = p >= thr
        svu[name] = {
            grp: {"n": int(mask.sum()), "detected": int(det[mask].sum()),
                  "recall": float(det[mask].mean())}
            for grp, mask in (("seen", test_attack["seen"].values), ("unseen", ~test_attack["seen"].values))}
    metrics["seen_vs_unseen"] = svu

    # ---- error analysis (deployed models on KDDTest+) ----------------------------------------
    p_bin = probas["binary"][("deployed", "B: KDDTest+")][:, 1]
    det_all = p_bin >= bundles["binary"]["threshold"]
    pred_mc = le.inverse_transform(probas["multiclass"][("deployed", "B: KDDTest+")].argmax(1))
    rows = []
    for atk, g in test[test["is_attack"] == 1].groupby("attack"):
        idx = g.index.values
        missed = int((~det_all[idx]).sum())
        mc_wrong = int((pred_mc[idx] != g["label5"].values).sum())
        top_conf = pd.Series(pred_mc[idx]).value_counts().index[0]
        rows.append({"attack": atk, "class": g["label5"].iloc[0], "n": int(len(g)),
                     "seen_in_train": atk in seen_attacks,
                     "binary_missed": missed, "binary_miss_rate": missed / len(g),
                     "multiclass_wrong": mc_wrong, "multiclass_error_rate": mc_wrong / len(g),
                     "multiclass_most_common_prediction": str(top_conf),
                     "mean_difficulty": float(g["difficulty"].mean())})
    per_attack = pd.DataFrame(rows).sort_values("binary_missed", ascending=False)
    metrics["error_analysis"] = {
        "binary_total_missed_attacks": int((~det_all[test["is_attack"].values == 1]).sum()),
        "binary_false_alarms": int(det_all[test["is_attack"].values == 0].sum()),
        "per_attack_type": per_attack.to_dict(orient="records"),
        "most_missed_binary": per_attack.head(10)[["attack", "class", "n", "binary_missed",
                                                   "binary_miss_rate", "seen_in_train"]].to_dict(orient="records"),
        "most_misclassified_multiclass": per_attack.sort_values("multiclass_wrong", ascending=False)
        .head(10)[["attack", "class", "n", "multiclass_wrong", "multiclass_error_rate",
                   "multiclass_most_common_prediction", "seen_in_train"]].to_dict(orient="records"),
    }

    # ======================= FIGURES =========================================================
    figs = {}
    # 1. model comparison (macro-F1, both protocols)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for ax, task in zip(axes, ("binary", "multiclass")):
        rec = [{"model": n, "protocol": d, "f1": metrics["protocols"][d][task][n]["f1_macro"]}
               for d in datasets for n in MODEL_ORDER]
        sns.barplot(pd.DataFrame(rec), x="model", y="f1", hue="protocol", palette=PROTO_COLOR, ax=ax,
                    order=MODEL_ORDER, width=0.75, edgecolor="white", linewidth=1.5)
        for c in ax.containers:
            ax.bar_label(c, fmt="%.3f", fontsize=8, padding=1)
        ax.set(title=f"{task.capitalize()} - macro-F1", xlabel="", ylabel="macro-F1", ylim=(0, 1.08))
        ax.tick_params(axis="x", rotation=15)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, fontsize=8, title="", frameon=False)
    figs["model_comparison"] = save(fig, "model_comparison.png")

    # 2. confusion matrices (deployed models, KDDTest+)
    for task, labels in (("binary", ["normal", "attack"]), ("multiclass", CLASSES)):
        cm = np.array(metrics["deployed"][task]["B: KDDTest+"]["confusion"])
        fig, axes = plt.subplots(1, 2, figsize=(11.5 if task == "multiclass" else 9, 4.6))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False, ax=axes[0],
                    xticklabels=labels, yticklabels=labels)
        axes[0].set(title=f"{task.capitalize()} ({best[task]}) - counts", xlabel="Predicted", ylabel="True")
        sns.heatmap(cm / cm.sum(1, keepdims=True), annot=True, fmt=".2f", cmap="Blues", vmin=0, vmax=1,
                    cbar=False, ax=axes[1], xticklabels=labels, yticklabels=labels)
        axes[1].set(title="Row-normalised (recall per class)", xlabel="Predicted", ylabel="")
        figs[f"confusion_{task}"] = save(fig, f"confusion_{task}.png")

    # 3. ROC + PR curves (binary, all models) on validation and KDDTest+
    fig, axes = plt.subplots(2, 2, figsize=(12, 9.5))
    for row, dname in enumerate(("A: validation", "B: KDDTest+")):
        y = datasets[dname]["is_attack"].values
        for name in MODEL_ORDER:
            p = probas["binary"][(name, dname)][:, 1]
            fpr, tpr, _ = roc_curve(y, p)
            prec, rec, _ = precision_recall_curve(y, p)
            axes[row, 0].plot(fpr, tpr, color=MODEL_COLOR[name], lw=2,
                              label=f"{name} (AUC {auc(fpr, tpr):.4f})")
            axes[row, 1].plot(rec, prec, color=MODEL_COLOR[name], lw=2,
                              label=f"{name} (AP {auc(rec, prec):.4f})")
        axes[row, 0].plot([0, 1], [0, 1], "--", color="#999", lw=1)
        axes[row, 0].set(title=f"ROC - {dname}", xlabel="False alarm rate (FPR)", ylabel="Detection rate (TPR)")
        axes[row, 1].set(title=f"Precision-Recall - {dname}", xlabel="Recall", ylabel="Precision")
        for ax in axes[row]:
            ax.legend(fontsize=8, loc="lower right" if ax is axes[row, 0] else "lower left")
    axes[0, 0].set_xlim(-0.005, 0.25)  # zoom into the useful low-FPR corner for validation
    figs["roc_pr_curves"] = save(fig, "roc_pr_curves.png")

    # 4. per-class recall (multiclass best model), Protocol A vs B, rare classes highlighted
    rec = [{"class": c, "protocol": d, "recall": metrics["protocols"][d]["multiclass"][best["multiclass"]]["per_class_recall"][c]}
           for d in datasets for c in CLASSES]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    sns.barplot(pd.DataFrame(rec), x="class", y="recall", hue="protocol", palette=PROTO_COLOR, ax=ax,
                order=CLASSES, edgecolor="white", linewidth=1.5)
    for c in ax.containers:
        ax.bar_label(c, fmt="%.2f", fontsize=8, padding=1)
    for i, c in enumerate(CLASSES):
        if c in ("R2L", "U2R"):
            ax.axvspan(i - 0.5, i + 0.5, color=PALETTE[2], alpha=0.10, zorder=0)
            ax.text(i, 1.03, "rare class", ha="center", fontsize=9, color=PALETTE[2], fontweight="bold")
    ax.set(title=f"Per-class recall - {best['multiclass']}", ylim=(0, 1.1), xlabel="", ylabel="Recall")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=8, title="", frameon=False)
    figs["per_class_recall"] = save(fig, "per_class_recall.png")

    # 5. seen vs unseen attacks (binary detection rate on KDDTest+)
    rec = [{"model": n, "group": f"{g} in training\n(n={svu[n][g]['n']})", "recall": svu[n][g]["recall"]}
           for n in MODEL_ORDER for g in ("seen", "unseen")]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    sns.barplot(pd.DataFrame(rec), x="model", y="recall", hue="group", palette=[PALETTE[1], PALETTE[4]],
                ax=ax, order=MODEL_ORDER, edgecolor="white", linewidth=1.5)
    for c in ax.containers:
        ax.bar_label(c, fmt="%.3f", fontsize=8, padding=1)
    ax.set(title="KDDTest+ detection rate: attack types SEEN vs UNSEEN in KDDTrain+",
           ylim=(0, 1.1), xlabel="", ylabel="Attack recall (detection rate)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=8, title="", frameon=False)
    figs["seen_vs_unseen"] = save(fig, "seen_vs_unseen.png")

    # 5b. per attack type detection (unseen types) for the deployed binary model
    pa = per_attack[per_attack["n"] >= 5].sort_values(["seen_in_train", "binary_miss_rate"],
                                                       ascending=[True, False])
    fig, ax = plt.subplots(figsize=(11, 6.5))
    colors = [PALETTE[4] if not s else PALETTE[1] for s in pa["seen_in_train"]]
    ax.barh(pa["attack"], 1 - pa["binary_miss_rate"], color=colors, edgecolor="white")
    for i, (r, n) in enumerate(zip(1 - pa["binary_miss_rate"], pa["n"])):
        ax.text(r + 0.01, i, f"{r:.2f}  (n={n})", va="center", fontsize=7.5)
    ax.invert_yaxis()
    ax.set(title=f"Detection rate per attack type on KDDTest+ ({best['binary']}, n>=5)",
           xlabel="Detection rate", xlim=(0, 1.25))
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=PALETTE[4]), plt.Rectangle((0, 0), 1, 1, color=PALETTE[1])],
              labels=["unseen in training", "seen in training"], fontsize=8, loc="upper center",
              bbox_to_anchor=(0.5, -0.08), ncol=2, frameon=False)
    figs["per_attack_detection"] = save(fig, "per_attack_detection.png")

    # 6. SHAP summary + top-15 importance for the best tree model (binary task)
    tree_models = [n for n in ("LightGBM", "XGBoost", "RandomForest")]
    shap_model = best["binary"] if best["binary"] in tree_models else max(
        tree_models, key=lambda n: metrics["protocols"]["A: validation"]["binary"][n]["f1_macro"])
    pipe = bundles["binary"]["pipeline"] if shap_model == best["binary"] else joblib.load(
        CANDIDATES_DIR / f"binary_{shap_model}.joblib")
    n_shap = 2000 if shap_model != "RandomForest" else 500  # RF TreeExplainer is ~50x slower
    sample = val.sample(n=n_shap, random_state=RANDOM_STATE)
    Xt = pipe["prep"].transform(sample[FEATURES])
    feat_names = list(pipe["prep"].get_feature_names_out())
    t0 = time.perf_counter()
    explainer = shap.TreeExplainer(pipe["clf"])
    sv = explainer.shap_values(Xt)
    if isinstance(sv, list):
        sv = sv[1]
    elif sv.ndim == 3:
        sv = sv[:, :, 1]
    shap_time = time.perf_counter() - t0
    imp = pd.Series(np.abs(sv).mean(0), index=feat_names).sort_values(ascending=False)
    plt.figure(figsize=(9, 8))
    shap.summary_plot(sv, Xt, feature_names=feat_names, max_display=20, show=False, plot_size=None)
    plt.title(f"SHAP summary - {shap_model} (binary, {n_shap} validation rows)", color=NAVY, fontweight="bold")
    figs["shap_summary"] = save(plt.gcf(), "shap_summary.png")
    fig, ax = plt.subplots(figsize=(9, 6))
    top = imp.head(15)[::-1]
    ax.barh(top.index, top.values, color=TEAL, edgecolor="white")
    ax.set(title=f"Top 15 features by mean |SHAP| - {shap_model}", xlabel="mean |SHAP value| (log-odds)")
    figs["feature_importance"] = save(fig, "feature_importance.png")
    metrics["shap"] = {"model": shap_model, "n_rows": n_shap, "time_s": shap_time,
                       "top15": [{"feature": f, "mean_abs_shap": float(v)} for f, v in imp.head(15).items()]}

    # 7. threshold vs recall / false-alarm (validation) + sensitivity table (val and KDDTest+)
    curve = pd.DataFrame(summary["tasks"]["binary"]["threshold"]["curve"])
    thr_info = summary["tasks"]["binary"]["threshold"]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(curve["threshold"], curve["recall"], color=PALETTE[1], lw=2.2, label="Attack recall")
    ax.plot(curve["threshold"], curve["false_alarm_rate"], color=PALETTE[4], lw=2.2, label="False-alarm rate")
    ax.axhline(thr_info["max_far_constraint"], ls="--", color="#888", lw=1, label="FAR budget (5%)")
    ax.axvline(thr_info["value"], ls=":", color=NAVY, lw=1.5,
               label=f"chosen threshold = {thr_info['value']:.3g}")
    ax.set_xscale("log")
    ax.set(title=f"Decision threshold trade-off on validation ({best['binary']})",
           xlabel="Threshold on P(attack)  (log scale)", ylabel="Rate", ylim=(0, 1.05))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=4, fontsize=8, frameon=False)
    figs["threshold_curve"] = save(fig, "threshold_curve.png")
    sens = []
    yv, yt = val["is_attack"].values, test["is_attack"].values
    pv = probas["binary"][(best["binary"], "A: validation")][:, 1]
    pt = probas["binary"][(best["binary"], "B: KDDTest+")][:, 1]
    for label, cut in [("chosen (max recall, FAR<=5%)", thr_info["value"]), ("0.01", 0.01), ("0.1", 0.1),
                       ("0.5 (default)", 0.5), ("0.9", 0.9)]:
        sens.append({"label": label, "threshold": cut,
                     "val_recall": float((pv[yv == 1] >= cut).mean()), "val_far": float((pv[yv == 0] >= cut).mean()),
                     "test_recall": float((pt[yt == 1] >= cut).mean()), "test_far": float((pt[yt == 0] >= cut).mean()),
                     "test_f1_macro": float(f1_score(yt, (pt >= cut).astype(int), average="macro"))})
    metrics["threshold_sensitivity"] = sens

    metrics["figures"] = figs
    metrics["eval_time_s"] = time.perf_counter() - t_start
    (REPORTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float))
    print(f"\nEvaluation done in {metrics['eval_time_s']:.0f}s -> {REPORTS_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
