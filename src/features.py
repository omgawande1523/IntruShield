"""IntruShield - preprocessing pipeline (fit on training data only)."""
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from config import CATEGORICAL, NUMERIC, SKEWED


def build_preprocessor(constant_cols: list[str], scale: bool) -> ColumnTransformer:
    """OneHot for categoricals, log1p for skewed counts, optional StandardScaler (linear models).

    constant_cols are dropped. All statistics (categories, scaler mean/std) are learned in .fit,
    which must only ever see KDDTrain+ rows.
    """
    skewed = [c for c in SKEWED if c not in constant_cols]
    plain = [c for c in NUMERIC if c not in constant_cols and c not in skewed]

    def numeric_steps(log: bool):
        steps = []
        if log:
            steps.append(("log1p", FunctionTransformer(np.log1p, feature_names_out="one-to-one")))
        if scale:
            steps.append(("scale", StandardScaler()))
        return Pipeline(steps) if steps else "passthrough"

    return ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float32),
             CATEGORICAL),
            ("log", numeric_steps(log=True), skewed),
            ("num", numeric_steps(log=False), plain),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
