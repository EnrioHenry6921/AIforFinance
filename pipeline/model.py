"""
model.py - Score 100% of entries.

Layer 1  Rules             : audit red flags for P1 Timing and P2 Amount (explainable)
Layer 2  Isolation Forest  : unsupervised - never sees the labels, finds the unusual
Layer 3  XGBoost (predict) : supervised - predicts P(anomaly); SHAP explains each prediction
Risk score = weighted mix of the three, 0-100.

Evaluation follows the professor's steps: split, train, evaluate, tune, decide.
Circularity test: the types in config.HELD_OUT_TYPES are NEVER shown to XGBoost.
"""
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score

from . import config
from .features import FEATURES

RULES = {  # weight of each red flag (points); manual entries count fully, system entries config.SYSTEM_WEIGHT
    "is_weekend": 25, "is_holiday": 25, "is_period_end": 10, "revenue_at_year_end": 30,
    "is_late_entry": 25, "is_night": 25, "entered_on_weekend": 5,
    "is_round": 25, "near_threshold": 15, "split_group": 25, "above_perf_mat": 15,
}
# is_manual is NOT given to the ML: all injected entries are manual, so it would leak the label
ML_FEATURES = [f for f in FEATURES if f != "is_manual"]
WEIGHTS = {"rules": 1.0, "iforest": 0.35, "xgb": 0.9}   # max contribution of each layer


def rules_score(e):
    pts = pd.DataFrame({f: e[f] * w for f, w in RULES.items()})
    pts = pts.mul(np.where(e["is_manual"] == 1, 1.0, config.SYSTEM_WEIGHT), axis=0)
    pts = pts.mul(np.where(e["is_recurring"] == 1, 0.3, 1.0), axis=0)   # rent, salaries: expected
    return pts.sum(axis=1).clip(upper=100), pts


def iforest_score(e):
    X = e[ML_FEATURES].astype(float)
    iso = IsolationForest(n_estimators=300, contamination="auto", random_state=0).fit(X)
    raw = -iso.score_samples(X)
    return pd.Series(raw, index=e.index).rank(pct=True)       # percentile 0-1


def _xgb(X, y):
    pos = max(int(y.sum()), 1)
    m = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.08, subsample=0.9,
                          colsample_bytree=0.9, scale_pos_weight=(len(y) - pos) / pos,
                          eval_metric="aucpr", random_state=0, n_jobs=4)
    return m.fit(X, y)


def _metrics(y, score, cutoff, k):
    flag = score >= cutoff
    tp = int((flag & (y == 1)).sum())
    top = score.sort_values(ascending=False).index[:k]
    prec, rec = tp / max(int(flag.sum()), 1), tp / max(int(y.sum()), 1)
    return {"precision": round(prec, 3),
            "recall": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "alerts": int(flag.sum()),
            f"precision_at_{k}": round(float(y.loc[top].mean()), 3),
            "pr_auc": round(float(average_precision_score(y, score)), 3) if y.sum() else None}


def score_all(e):
    e = e.copy()
    y = e["is_anomaly"].astype(int)
    held = e["anomaly_type"].isin(config.HELD_OUT_TYPES)

    # Layer 1 + 2
    e["rules_score"], rule_pts = rules_score(e)
    e["iforest_pct"] = iforest_score(e)

    if y.sum() == 0:                                   # no labels (real data only): no supervised model
        return _unsupervised_only(e)

    # ---- Evaluation split: train 2023 (without held-out types) / test 2024 + all held-out anomalies
    year = e["posting_date"].dt.year
    first = year.min()
    train = (year == first) & ~held
    test = ~train
    m_eval = _xgb(e.loc[train, ML_FEATURES].astype(float), y[train])
    p_test = pd.Series(m_eval.predict_proba(e.loc[test, ML_FEATURES].astype(float))[:, 1], index=e.index[test])

    # ---- Final model for scoring: all labelled data except held-out types
    m = _xgb(e.loc[~held, ML_FEATURES].astype(float), y[~held])
    X = e[ML_FEATURES].astype(float)
    e["xgb_proba"] = m.predict_proba(X)[:, 1]
    e.loc[test, "xgb_proba_eval"] = p_test
    shap = m.get_booster().predict(xgb.DMatrix(X), pred_contribs=True)[:, :-1]   # SHAP values per feature
    shap = pd.DataFrame(shap, columns=ML_FEATURES, index=e.index)

    # ---- Composite risk score
    # "Any strong signal" blend (noisy-OR): one clear red flag, a confident model OR a strong
    # outlier is enough to raise the score - so patterns the ML never saw are still caught by the rules.
    r = (e["rules_score"] / 50).clip(upper=1)
    i = ((e["iforest_pct"] - 0.9) / 0.1).clip(lower=0)          # only the top 10% of outliers count
    x = e["xgb_proba"]
    e["risk_score"] = (100 * (1 - (1 - WEIGHTS["rules"] * r) * (1 - WEIGHTS["xgb"] * x)
                              * (1 - WEIGHTS["iforest"] * i))).round(1)
    e["alert"] = (e["risk_score"] >= config.ALERT_CUTOFF).astype(int)

    # ---- Explanations kept for the website/memo
    e["rule_hits"] = [[FEATURES[f] for f in rule_pts.columns if rule_pts.at[i, f] > 0] for i in e.index]
    top_shap = []
    for i in e.index:
        s = shap.loc[i].sort_values(ascending=False)
        top_shap.append([{"feature": FEATURES[f], "shap": round(float(v), 3)} for f, v in s.items() if v > 0.05][:5])
    e["shap_top"] = top_shap

    # ---- Metrics
    k = max(int(y.sum()), 1)
    ev = {}
    for name, col, cut in [("Rules", "rules_score", 25), ("Isolation Forest", "iforest_pct", 0.995),
                           ("XGBoost", "xgb_proba", 0.5), ("Risk score (combined)", "risk_score", config.ALERT_CUTOFF)]:
        ev[name] = _metrics(y, e[col], cut, k)
    ev_test = _metrics(y[test], p_test, 0.5, max(int(y[test].sum()), 1))

    by_type = []
    for t, s in e[y == 1].groupby("anomaly_type"):
        by_type.append({
            "type": t, "n": int(len(s)), "held_out": t in config.HELD_OUT_TYPES,
            "rules": round(float((s["rules_score"] >= 25).mean()), 2),
            "iforest": round(float((s["iforest_pct"] >= 0.995).mean()), 2),
            "xgboost": round(float((s["xgb_proba"] >= 0.5).mean()), 2),
            "combined": round(float((s["risk_score"] >= config.ALERT_CUTOFF).mean()), 2),
        })
    importance = sorted(({"feature": FEATURES[f], "importance": round(float(v), 4)}
                         for f, v in zip(ML_FEATURES, m.feature_importances_)), key=lambda d: -d["importance"])
    metrics = {"models": ev, "xgb_test_2024_and_held_out": ev_test, "by_type": by_type,
               "feature_importance": importance, "weights": WEIGHTS, "rules": RULES,
               "held_out_types": config.HELD_OUT_TYPES,
               "split": f"XGBoost trained on {first} without held-out types; tested on later year + held-out types"}
    return e.sort_values("risk_score", ascending=False).reset_index(drop=True), metrics


def _unsupervised_only(e):
    """Without labelled anomalies XGBoost cannot learn: score with rules + Isolation Forest only."""
    r = (e["rules_score"] / 50).clip(upper=1)
    i = ((e["iforest_pct"] - 0.9) / 0.1).clip(lower=0)
    e["xgb_proba"] = 0.0
    e["risk_score"] = (100 * (1 - (1 - WEIGHTS["rules"] * r) * (1 - WEIGHTS["iforest"] * i))).round(1)
    e["alert"] = (e["risk_score"] >= config.ALERT_CUTOFF).astype(int)
    _, pts = rules_score(e)
    e["rule_hits"] = [[FEATURES[f] for f in pts.columns if pts.at[i, f] > 0] for i in e.index]
    e["shap_top"] = [[] for _ in e.index]
    na = {"precision": None, "recall": None, "f1": None, "alerts": None, "precision_at_0": None, "pr_auc": None}
    metrics = {"models": {"Risk score (combined)": {**na, "alerts": int(e["alert"].sum())}},
               "xgb_test_2024_and_held_out": na, "by_type": [], "feature_importance": [], "weights": WEIGHTS,
               "rules": RULES, "held_out_types": [], "split": "no labelled anomalies: rules + Isolation Forest only"}
    return e.sort_values("risk_score", ascending=False).reset_index(drop=True), metrics


def forecast_revenue(lines):
    """Predictive analytics (plan option B): expected monthly revenue vs actual.
    Expected = same month last year x running growth of the year so far. Flag months outside the band."""
    rev = lines[lines["account"] == "8400"].groupby(lines["posting_date"].dt.to_period("M"))["credit"].sum()
    rev.index = rev.index.to_timestamp()
    out = []
    years = sorted(rev.index.year.unique())
    if len(years) < 2:
        return {"months": [], "note": "needs 2 years of history"}
    base = rev[rev.index.year == years[0]]
    ratios = []
    for t, actual in rev[rev.index.year > years[0]].items():
        ly = base.get(pd.Timestamp(t.year - 1, t.month, 1))
        ytd_now = rev[(rev.index.year == t.year) & (rev.index < t)]
        ytd_ly = base[base.index.month.isin(ytd_now.index.month)]
        growth = ytd_now.sum() / ytd_ly.sum() if len(ytd_now) and ytd_ly.sum() else 1.0
        exp = float(ly * growth) if ly is not None else float("nan")
        ratios.append(actual / exp if exp else 1)
        out.append({"month": t.strftime("%Y-%m"), "actual": round(float(actual), 2), "expected": round(exp, 2)})
    sd = float(np.std(np.log(ratios))) if ratios else 0.1
    band = max(0.10, 2 * sd)
    for o in out:
        o["low"], o["high"] = round(o["expected"] * (1 - band), 2), round(o["expected"] * (1 + band), 2)
        o["flag"] = bool(o["actual"] > o["high"] or o["actual"] < o["low"])
    hist = [{"month": t.strftime("%Y-%m"), "actual": round(float(v), 2)} for t, v in base.items()]
    return {"history": hist, "months": out, "band_pct": round(band * 100, 1),
            "method": "Seasonal naive (same month last year) x running year-to-date growth; band = 2 x std of log errors"}
