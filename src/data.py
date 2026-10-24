"""IntruShield - data download, loading, labelling and audit."""
import json
import sys
import urllib.request

import pandas as pd

from config import (ATTACK_MAP, COLUMNS, DATA_DIR, FEATURES, FILES, LABEL_TO_CLASS, RAW_BASE,
                    REPORTS_DIR)


def download() -> None:
    for fname in FILES.values():
        dest = DATA_DIR / fname
        if dest.exists() and dest.stat().st_size > 0:
            continue
        url = RAW_BASE + fname
        print(f"Downloading {url}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:  # noqa: BLE001
            sys.exit(f"Download of {fname} failed ({exc}). Place KDDTrain+.txt, KDDTest+.txt and "
                     f"KDDTest-21.txt manually in {DATA_DIR} and re-run.")


def load_split(name: str) -> pd.DataFrame:
    """Return a DataFrame with 41 features + attack, difficulty, label5, is_attack."""
    df = pd.read_csv(DATA_DIR / FILES[name], header=None, names=COLUMNS)
    df["attack"] = df["attack"].str.strip().str.rstrip(".")
    unmapped = sorted(set(df["attack"]) - set(LABEL_TO_CLASS))
    if unmapped:
        sys.exit(f"Unmapped attack labels in {FILES[name]}: {unmapped}. Extend ATTACK_MAP in "
                 f"src/config.py.")
    df["label5"] = df["attack"].map(LABEL_TO_CLASS)
    df["is_attack"] = (df["label5"] != "Normal").astype(int)
    return df


def audit(train: pd.DataFrame, test: pd.DataFrame, test21: pd.DataFrame) -> dict:
    train_attacks, test_attacks = set(train["attack"]), set(test["attack"])
    const_cols = [c for c in FEATURES if train[c].nunique() == 1]
    unseen = sorted(test_attacks - train_attacks)
    info = {
        "rows": {"train": len(train), "test": len(test), "test21": len(test21)},
        "duplicate_rows": {
            "train": int(train[FEATURES + ["attack"]].duplicated().sum()),
            "test": int(test[FEATURES + ["attack"]].duplicated().sum()),
            "test_rows_also_in_train": int(
                test[FEATURES].merge(train[FEATURES].drop_duplicates(), how="inner").shape[0]),
        },
        "class_distribution": {
            "train": train["label5"].value_counts().to_dict(),
            "test": test["label5"].value_counts().to_dict(),
            "test21": test21["label5"].value_counts().to_dict(),
        },
        "binary_distribution": {
            "train": train["is_attack"].value_counts().rename({0: "normal", 1: "attack"}).to_dict(),
            "test": test["is_attack"].value_counts().rename({0: "normal", 1: "attack"}).to_dict(),
        },
        "n_attack_types": {"train": len(train_attacks), "test": len(test_attacks)},
        "constant_columns": const_cols,
        "attacks_in_test_not_in_train": {
            a: {"class": LABEL_TO_CLASS[a], "test_rows": int((test["attack"] == a).sum())}
            for a in unseen},
        "unseen_attack_rows_in_test": int(test["attack"].isin(unseen).sum()),
        "attack_map": ATTACK_MAP,
        "difficulty_mean": {"train": float(train["difficulty"].mean()),
                            "test": float(test["difficulty"].mean())},
    }
    (REPORTS_DIR / "audit.json").write_text(json.dumps(info, indent=2))
    return info


if __name__ == "__main__":
    download()
    tr, te, te21 = load_split("train"), load_split("test"), load_split("test21")
    a = audit(tr, te, te21)
    print(json.dumps({k: v for k, v in a.items() if k != "attack_map"}, indent=2))
    print(f"Audit written to {REPORTS_DIR / 'audit.json'}")
