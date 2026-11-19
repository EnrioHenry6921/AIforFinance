"""
person2_model.py - Person 2's trained classifier, usable with ANY scikit-learn version.

Person 2 trained a HistGradientBoostingClassifier on the DIB ledger's own labels
(850 labelled anomalies, temporal split at 2024-07-08: recall 97.5%, precision 37%).
Their .joblib file only loads with scikit-learn 1.4.0, which does not install on Python 3.13.
`tools/export_person2_model.py` converted it to a plain JSON file (same trees, same thresholds);
this module scores with NumPy and reproduces Person 2's scores exactly (tested in tests/).

Features are rebuilt exactly as in Person 2's ml_inference.py (_prepare_entry_level).
"""
import json
from functools import lru_cache

import numpy as np
import pandas as pd

from . import config


@lru_cache(maxsize=2)
def load(path=None):
    path = path or config.PERSON2_MODEL
    with open(path) as f:
        m = json.load(f)
    if m.get("format") != "journalguard-hgb-v1":
        raise ValueError(f"{path} is not an exported Person 2 model")
    for t in m["trees"]:
        for k in t:
            t[k] = np.asarray(t[k])
    return m


def available():
    return config.PERSON2_MODEL.exists()


def features(lines):
    """The 12 Person 2 features, one row per entry (index = entry_id)."""
    g = lines.groupby("entry_id", sort=False)
    e = pd.DataFrame({
        "posting_date": g["posting_date"].first(),
        "document_date": g["document_date"].first(),
        "entered_at": g["entered_at"].first(),
        "user": g["user"].first().astype(str),
        "posting_line_count": g["account"].count(),
        "account_count": g["account"].nunique(),
        "account_signature": g["account"].agg(lambda s: "|".join(sorted(set(s.astype(str))))),
        "total_debit": g["debit"].sum().round(2),
        "total_credit": g["credit"].sum().round(2),
    })
    e["log_entry_amount"] = np.log1p(np.maximum(e["total_debit"], e["total_credit"]).clip(lower=0))
    e["posting_weekday"] = e["posting_date"].dt.weekday
    e["posting_month"] = e["posting_date"].dt.month
    e["posting_day"] = e["posting_date"].dt.day
    e["posting_hour"] = e["entered_at"].dt.hour.fillna(0).astype(int)
    e["doc_to_post_days"] = ((e["posting_date"] - e["document_date"]).dt.total_seconds() / 86400.0).round(2)
    e["post_to_enter_days"] = (e["entered_at"].dt.normalize() - e["posting_date"].dt.normalize()).dt.days.astype(float)
    e["user_entry_count"] = e["user"].map(e["user"].value_counts()).astype(int)
    return e


def _matrix(e, m):
    cols = [e[c].astype(float).to_numpy() for c in m["numeric_features"]]
    for feat, cats in zip(m["categorical_features"], m["categories"]):
        v = e[feat].astype(str).to_numpy()
        cols += [(v == c).astype(float) for c in cats]          # unknown category -> all zeros (handle_unknown="ignore")
    return np.column_stack(cols)


def _tree(X, t):
    node = np.zeros(len(X), dtype=int)
    for _ in range(64):                                         # depth is at most 5; loop until all rows sit on a leaf
        leaf = t["is_leaf"][node].astype(bool)
        if leaf.all():
            break
        idx = np.where(~leaf)[0]
        n = node[idx]
        x = X[idx, t["feature_idx"][n]]
        go_left = np.where(np.isnan(x), t["missing_go_to_left"][n].astype(bool), x <= t["num_threshold"][n])
        node[idx] = np.where(go_left, t["left"][n], t["right"][n])
    return t["value"][node]


def predict_proba(e, path=None):
    m = load(path)
    X = _matrix(e, m)
    raw = np.full(len(X), m["baseline"])
    for t in m["trees"]:
        raw += _tree(X, t)
    return 1 / (1 + np.exp(-raw))


def score(lines, path=None):
    """Return a DataFrame: entry_id, p2_score (0-100), p2_level, p2_predicted, applicable."""
    e = features(lines)
    p = predict_proba(e, path)
    m = load(path)
    known_users = set(m["categories"][m["categorical_features"].index("user")])
    applicable = e["user"].isin(known_users).mean() > 0.5     # trained on DIB users/accounts only
    out = pd.DataFrame({"entry_id": e.index, "p2_score": (p * 100).round(1)})
    out["p2_level"] = np.where(out["p2_score"] >= 70, "High", np.where(out["p2_score"] >= 40, "Medium", "Low"))
    out["p2_predicted"] = (p >= 0.5).astype(int)
    return out.reset_index(drop=True), bool(applicable)
