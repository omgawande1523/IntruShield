"""IntruShield - train, tune, select and persist binary + multiclass models.

Protocol: stratified 85/15 split of KDDTrain+; all tuning / selection / thresholding on the 15%
validation split; KDDTest+ is never touched here.
"""
import json
import os
import time
import warnings

import joblib
import numpy as np
from lightgbm import LGBMClassifier
from scipy.stats import randint, uniform
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_curve
from sklearn.model_selection import (RandomizedSearchCV, StratifiedKFold, cross_val_score,
                                     train_test_split)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from config import CANDIDATES_DIR, CLASSES, FEATURES, MODELS_DIR, RANDOM_STATE, REPORTS_DIR
from data import load_split
from features import build_preprocessor

warnings.filterwarnings("ignore")
N_CPU = os.cpu_count() or 4
MAX_FAR = 0.05  # max false-alarm rate allowed when choosing the binary threshold


def make_estimators(task: str, n_jobs: int) -> dict:
    """Base (untuned) estimators. task in {'binary','multiclass'}."""
    n_cls = 2 if task == "binary" else len(CLASSES)
    return {
        "LogisticRegression": LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0,
                                                 random_state=RANDOM_STATE),
        "RandomForest": RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample",
                                               n_jobs=n_jobs, random_state=RANDOM_STATE),
        "XGBoost": XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
                                 tree_method="hist", n_jobs=n_jobs, random_state=RANDOM_STATE,
                                 objective="binary:logistic" if n_cls == 2 else "multi:softprob",
                                 eval_metric="logloss" if n_cls == 2 else "mlogloss"),
        "LightGBM": LGBMClassifier(n_estimators=300, num_leaves=63, learning_rate=0.1,
                                   class_weight="balanced", n_jobs=n_jobs, verbose=-1,
                                   random_state=RANDOM_STATE),
    }


# Learning-rate ranges are capped: with class-balanced weights (U2R weight ~500x) a boosting rate above
# ~0.2 makes multiclass LightGBM/XGBoost diverge on some folds (observed macro-F1 0.28-0.96 across folds).
SEARCH_SPACES = {
    "XGBoost": {
        "clf__n_estimators": randint(100, 300),
        "clf__max_depth": randint(4, 9),
        "clf__learning_rate": uniform(0.03, 0.17),
        "clf__subsample": uniform(0.6, 0.4),
        "clf__colsample_bytree": uniform(0.5, 0.5),
        "clf__min_child_weight": randint(1, 6),
        "clf__reg_lambda": uniform(0.5, 4.5),
    },
    "LightGBM": {
        "clf__n_estimators": randint(100, 400),
        "clf__num_leaves": randint(15, 96),
        "clf__learning_rate": uniform(0.03, 0.12),
        "clf__subsample": uniform(0.6, 0.4),
        "clf__subsample_freq": [1],
        "clf__colsample_bytree": uniform(0.5, 0.5),
        "clf__min_child_samples": randint(20, 80),
        "clf__reg_lambda": uniform(0.5, 4.5),
    },
}


def make_pipeline(name: str, est, constant_cols):
    return Pipeline([("prep", build_preprocessor(constant_cols, scale=name == "LogisticRegression")),
                     ("clf", est)])


def fit_kwargs(name: str, y):
    """XGBoost gets balanced sample weights; the others use class_weight."""
    if name == "XGBoost":
        return {"clf__sample_weight": compute_sample_weight("balanced", y)}
    return {}


def choose_threshold(y_true, p_attack, max_far=MAX_FAR):
    """Maximise attack recall subject to validation FPR <= max_far.

    Recall is monotone non-increasing in the threshold, so the optimum is the LOWEST score threshold
    whose false-alarm rate still respects the budget. When validation is (nearly) separable this
    deliberately spends the whole false-alarm budget on sensitivity - the a-priori choice for a
    detector that must face attack types absent from validation.
    """
    fpr, tpr, thr = roc_curve(y_true, p_attack, drop_intermediate=False)
    ok = np.where(fpr <= max_far)[0]
    best = ok[-1]  # fpr/tpr are non-decreasing along the curve -> last feasible index = max recall
    t = float(min(thr[best], 1.0))
    grid = np.unique(np.concatenate([np.logspace(-7, 0, 120), [0.5]]))
    curve = []
    for cut in grid:
        pred = (p_attack >= cut).astype(int)
        curve.append({"threshold": float(cut),
                      "recall": float(pred[y_true == 1].mean()),
                      "false_alarm_rate": float(pred[y_true == 0].mean())})
    return t, float(tpr[best]), float(fpr[best]), curve


def run_task(task, X_tr, y_tr, X_val, y_val, constant_cols, log):
    results, fitted = {}, {}
    base = make_estimators(task, n_jobs=N_CPU)
    cv3 = StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_STATE)
    for name, est in base.items():
        best_params = {}
        if name in SEARCH_SPACES:
            # single-threaded estimator clones inside a fully parallel search (no oversubscription)
            search_est = make_estimators(task, n_jobs=1)[name]
            search = RandomizedSearchCV(
                make_pipeline(name, search_est, constant_cols), SEARCH_SPACES[name], n_iter=12,
                cv=cv3, scoring="f1_macro", n_jobs=-1, random_state=RANDOM_STATE, refit=False)
            t0 = time.perf_counter()
            search.fit(X_tr, y_tr, **fit_kwargs(name, y_tr))
            best_params = {k.replace("clf__", ""): (v.item() if hasattr(v, "item") else v)
                           for k, v in search.best_params_.items()}
            est.set_params(**best_params)
            log(f"  [{task}] {name} tuned in {time.perf_counter() - t0:.0f}s, "
                f"cv f1_macro={search.best_score_:.4f} params={best_params}")
        pipe = make_pipeline(name, est, constant_cols)
        t0 = time.perf_counter()
        pipe.fit(X_tr, y_tr, **fit_kwargs(name, y_tr))
        train_time = time.perf_counter() - t0
        f1 = f1_score(y_val, pipe.predict(X_val), average="macro")
        log(f"  [{task}] {name}: val macro-F1={f1:.4f}  train={train_time:.1f}s")
        results[name] = {"val_f1_macro": float(f1), "train_time_s": float(train_time),
                         "best_params": best_params}
        fitted[name] = pipe
        joblib.dump(pipe, CANDIDATES_DIR / f"{task}_{name}.joblib")
    best = max(results, key=lambda n: results[n]["val_f1_macro"])
    log(f"  [{task}] BEST = {best}")
    return best, results, fitted


def main():
    t_start = time.perf_counter()
    lines = []

    def log(msg):
        print(msg, flush=True)
        lines.append(msg)

    train = load_split("train")
    constant_cols = [c for c in FEATURES if train[c].nunique() == 1]
    log(f"Dropping constant columns: {constant_cols}")
    X, y5, yb = train[FEATURES], train["label5"], train["is_attack"]
    # One stratified split shared by both tasks (stratify on the 5-class label).
    idx_tr, idx_val = train_test_split(np.arange(len(train)), test_size=0.15,
                                       stratify=y5, random_state=RANDOM_STATE)
    X_tr, X_val = X.iloc[idx_tr], X.iloc[idx_val]
    le = LabelEncoder().fit(CLASSES)
    y5_tr, y5_val = le.transform(y5.iloc[idx_tr]), le.transform(y5.iloc[idx_val])
    yb_tr, yb_val = yb.iloc[idx_tr].values, yb.iloc[idx_val].values
    log(f"Train/val split: {len(idx_tr)} / {len(idx_val)} rows")

    # Duplicate-leakage check between the two halves of the split (feature vectors only)
    dup_val_in_tr = int(X_val.merge(X_tr.drop_duplicates(), how="inner").shape[0])
    log(f"Validation rows whose feature vector also appears in train split: {dup_val_in_tr}")

    summary = {"split": {"train_rows": int(len(idx_tr)), "val_rows": int(len(idx_val)),
                         "val_rows_duplicated_in_train": dup_val_in_tr},
               "constant_cols": constant_cols, "classes": CLASSES, "tasks": {}}

    for task, (ytr, yval) in {"binary": (yb_tr, yb_val), "multiclass": (y5_tr, y5_val)}.items():
        log(f"\n=== {task.upper()} ===")
        best, results, fitted = run_task(task, X_tr, ytr, X_val, yval, constant_cols, log)
        best_pipe = fitted[best]

        # 5-fold stratified CV of the best configuration on the full KDDTrain+
        y_full = yb.values if task == "binary" else le.transform(y5)
        cv5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        t0 = time.perf_counter()
        scores = cross_val_score(best_pipe, X, y_full, cv=cv5, scoring="f1_macro",
                                 n_jobs=1, params=fit_kwargs(best, y_full))
        log(f"  [{task}] 5-fold CV macro-F1 on KDDTrain+: {scores.mean():.4f} +/- {scores.std():.4f} "
            f"({time.perf_counter() - t0:.0f}s)")

        bundle = {"task": task, "model_name": best, "classes": CLASSES, "label_encoder": le,
                  "constant_cols": constant_cols, "best_params": results[best]["best_params"],
                  "cv5_f1_macro_mean": float(scores.mean()), "cv5_f1_macro_std": float(scores.std())}
        task_info = {"best_model": best, "models": results,
                     "cv5_f1_macro": {"mean": float(scores.mean()), "std": float(scores.std()),
                                      "folds": scores.tolist()}}
        if task == "binary":
            p_val = best_pipe.predict_proba(X_val)[:, 1]
            thr, rec, far, curve = choose_threshold(yval, p_val)
            log(f"  [binary] threshold={thr:.3g} -> val recall={rec:.4f}, false-alarm={far:.4f} "
                f"(constraint FAR<={MAX_FAR})")
            bundle["threshold"] = thr
            task_info["threshold"] = {"value": thr, "val_recall": rec, "val_false_alarm_rate": far,
                                      "max_far_constraint": MAX_FAR, "curve": curve}
            # thresholds for every candidate so evaluate.py can apply the same rule to all
            task_info["candidate_thresholds"] = {
                n: choose_threshold(yval, m.predict_proba(X_val)[:, 1])[0] for n, m in fitted.items()}

        # Refit best model on the full KDDTrain+ and persist the deployable bundle
        t0 = time.perf_counter()
        final = make_pipeline(best, make_estimators(task, N_CPU)[best].set_params(
            **results[best]["best_params"]), constant_cols)
        final.fit(X, y_full, **fit_kwargs(best, y_full))
        bundle["pipeline"] = final
        bundle["refit_time_s"] = time.perf_counter() - t0
        path = MODELS_DIR / f"{task}_model.joblib"
        joblib.dump(bundle, path)
        log(f"  [{task}] refit on full KDDTrain+ in {bundle['refit_time_s']:.1f}s -> {path}")
        summary["tasks"][task] = task_info

    np.save(MODELS_DIR / "val_idx.npy", idx_val)
    summary["total_train_time_s"] = time.perf_counter() - t_start
    (REPORTS_DIR / "train_summary.json").write_text(json.dumps(summary, indent=2))
    log(f"\nTraining stage done in {summary['total_train_time_s']:.0f}s")


if __name__ == "__main__":
    main()
