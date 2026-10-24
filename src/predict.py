"""IntruShield - demo: score 10 random KDDTest+ connections with the saved models + SHAP reasons."""
import warnings

import joblib
import numpy as np
import shap

from config import FEATURES, MODELS_DIR, RANDOM_STATE
from data import load_split

warnings.filterwarnings("ignore")


def shap_reasons(pipe, X, top=3):
    """Top-k signed SHAP contributions (log-odds) toward 'attack' for each row of X."""
    clf, prep = pipe["clf"], pipe["prep"]
    Xt = prep.transform(X)
    names = prep.get_feature_names_out()
    if hasattr(clf, "coef_"):  # linear model: contribution = coef * standardized value
        sv = Xt * clf.coef_[0]
    else:
        sv = shap.TreeExplainer(clf).shap_values(Xt)
        if isinstance(sv, list):
            sv = sv[1]
        elif sv.ndim == 3:
            sv = sv[:, :, 1]
    out = []
    for i in range(len(X)):
        order = np.argsort(-np.abs(sv[i]))[:top]
        out.append([(names[j], float(Xt[i, j]), float(sv[i, j])) for j in order])
    return out


def main(n=10):
    binary = joblib.load(MODELS_DIR / "binary_model.joblib")
    multi = joblib.load(MODELS_DIR / "multiclass_model.joblib")
    test = load_split("test")
    rows = test.sample(n=n, random_state=RANDOM_STATE)
    X = rows[FEATURES]
    p_attack = binary["pipeline"].predict_proba(X)[:, 1]
    is_attack = p_attack >= binary["threshold"]
    cls = multi["label_encoder"].inverse_transform(multi["pipeline"].predict(X))
    reasons = shap_reasons(binary["pipeline"], X)

    print(f"IntruShield demo - binary={binary['model_name']} (threshold {binary['threshold']:.3g}), "
          f"multiclass={multi['model_name']}\n")
    hdr = f"{'#':>2} {'true attack':<16}{'true class':<11}{'pred':<8}{'pred class':<11}{'P(attack)':>9}  top-3 SHAP reasons"
    print(hdr)
    print("-" * len(hdr))
    for k, (idx, r) in enumerate(rows.iterrows()):
        pred = "ATTACK" if is_attack[k] else "normal"
        pred_cls = cls[k] if is_attack[k] else "Normal"
        why = "; ".join(f"{f}={v:.2f} ({s:+.2f})" for f, v, s in reasons[k])
        flag = "" if (pred_cls == r['label5']) else "  <-- wrong"
        print(f"{k + 1:>2} {r['attack']:<16}{r['label5']:<11}{pred:<8}{pred_cls:<11}{p_attack[k]:>9.4f}  {why}{flag}")
    print("\nSHAP value = contribution to log-odds of 'attack' (+ pushes toward attack); feature values "
          "shown after log1p / one-hot preprocessing.")


if __name__ == "__main__":
    main()
