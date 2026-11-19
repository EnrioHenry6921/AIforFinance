"""
model.py - Score 100% of entries and evaluate honestly.

Layer 1  Rules             : audit red flags (P1 Timing, P2 Amount, Context) - explainable
Layer 2  Unsupervised      : Isolation Forest, LOF, Autoencoder (never see the labels).
                             The autoencoder is kept only if it beats Isolation Forest clearly
                             (brief: "if it brings no clear gain, keep the simpler model").
Layer 3  XGBoost (ours)    : predicts P(anomaly); SHAP explains each prediction
Layer 4  Person 2's model  : HistGradientBoosting trained by Person 2 on the DIB labels
Risk score = "any strong signal" blend of the layers, 0-100.

Evaluation (professor's steps: split, train, evaluate, decide):
  * temporal split - the last TEST_SHARE of the period is the test set (like Person 2)
  * held-out types - some anomaly types are NEVER shown to XGBoost (circularity test)
  * every metric is computed on rows the supervised model never trained on.
  * Person 2's model was trained on ALL labels, so it is in-sample on any split of the DIB
    ledger: its own reported temporal-test metrics are shown instead, and the honest combined
    score is evaluated without it.
"""
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import RobustScaler

from . import config
from .features import label_of, ml_features, user_columns

RULES = {  # points per red flag; manual entries count fully, system entries SYSTEM_WEIGHT
    "is_weekend": 25, "is_holiday": 20, "is_period_end": 10, "revenue_at_year_end": 30,
    "is_delayed_entry": 12, "is_late_entry": 25, "is_night": 25, "entered_on_weekend": 5,
    "is_round": 25, "near_threshold": 15, "split_group": 25, "above_perf_mat": 15, "high_cash": 30,
    "rare_account_combo": 20, "new_account": 20, "user_unusual_hour": 10, "possible_duplicate": 30,
}
WEIGHTS = {"rules": 1.0, "xgb": 0.9, "person2": 0.9, "unsupervised": 0.35}
CUT = {"rules": 25, "pct": 0.995, "proba": 0.5}


# ---------------------------------------------------------------- layers
def rules_score(e):
    pts = pd.DataFrame({f: e[f] * w for f, w in RULES.items() if f in e})
    pts = pts.mul(np.where(e["is_manual"] == 1, 1.0, config.SYSTEM_WEIGHT), axis=0)
    pts = pts.mul(np.where(e["is_recurring"] == 1, 0.3, 1.0), axis=0)
    return pts.sum(axis=1).clip(upper=100), pts


def _scaled(e, cols):
    X = e[cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy()
    return RobustScaler().fit_transform(X)


def unsupervised(e, cols, seed=0):
    """Isolation Forest, LOF and an autoencoder; each returns a 0-1 percentile (1 = most unusual)."""
    X = _scaled(e, cols)
    rng = np.random.default_rng(seed)
    sample = rng.choice(len(X), size=min(len(X), 30000), replace=False)
    out = {}
    iso = IsolationForest(n_estimators=300, random_state=seed, n_jobs=-1).fit(X[sample])
    out["iforest"] = -iso.score_samples(X)
    n_nb = min(35, max(5, len(sample) // 50))
    lof = LocalOutlierFactor(n_neighbors=n_nb, novelty=True).fit(X[sample[:20000]])
    out["lof"] = -lof.score_samples(X)
    width = max(4, X.shape[1] // 2)
    ae = MLPRegressor(hidden_layer_sizes=(width, max(2, width // 2), width), max_iter=60, random_state=seed,
                      early_stopping=True).fit(X[sample], X[sample])
    out["autoencoder"] = ((ae.predict(X) - X) ** 2).mean(axis=1)
    return {k: pd.Series(v, index=e.index).rank(pct=True) for k, v in out.items()}


def _xgb(X, y):
    pos = max(int(y.sum()), 1)
    m = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9,
                          scale_pos_weight=np.sqrt((len(y) - pos) / pos), eval_metric="aucpr", random_state=0, n_jobs=4)
    return m.fit(X, y)


def _best_threshold(y, p):
    """Probability cut that maximises F1 on validation rows (XGBoost's raw 0.5 is meaningless with class weights)."""
    from sklearn.metrics import precision_recall_curve
    if y.sum() == 0:
        return 0.5
    pr, rc, th = precision_recall_curve(y, p)
    f1 = 2 * pr[:-1] * rc[:-1] / np.maximum(pr[:-1] + rc[:-1], 1e-9)
    return float(np.clip(th[int(np.argmax(f1))], 0.05, 0.99))


def _xgb_fit_tuned(X, y, dates):
    """Fit on the earlier 75% of the rows given, pick the F1-best cut on the later 25%, refit on all of them."""
    cut = dates.quantile(0.75)
    inner, val = dates < cut, dates >= cut
    t = 0.5
    if y[inner].sum() >= 3 and y[val].sum() >= 1:
        t = _best_threshold(y[val], _xgb(X[inner], y[inner]).predict_proba(X[val])[:, 1])
    return _xgb(X, y), t


def signal(p, t):
    """Map a probability to a 0-1 signal on the log-odds scale, so the model's own cut t lands on 0.6
    (risk 54 = an alert) and a probability just under an extreme cut (0.93 vs 0.99) stays well below it."""
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    t = float(np.clip(t, 1e-6, 1 - 1e-6))
    z = np.log(p / (1 - p)) - np.log(t / (1 - t)) + np.log(1.5)
    return 1 / (1 + np.exp(-z))


def _blend(rules, xgb_p=None, p2=None, unsup=None):
    r = (rules / 50).clip(upper=1)
    keep = 1 - WEIGHTS["rules"] * r
    if xgb_p is not None:
        keep = keep * (1 - WEIGHTS["xgb"] * xgb_p)
    if p2 is not None:
        keep = keep * (1 - WEIGHTS["person2"] * p2)
    if unsup is not None:
        keep = keep * (1 - WEIGHTS["unsupervised"] * ((unsup - 0.9) / 0.1).clip(lower=0))
    return (100 * (1 - keep)).round(1)


def _metrics(y, score, cutoff, k):
    if len(y) == 0:
        return {"precision": None, "recall": None, "f1": None, "alerts": 0, "precision_at_k": None, "pr_auc": None}
    flag = score >= cutoff
    tp = int((flag & (y == 1)).sum())
    prec, rec = tp / max(int(flag.sum()), 1), tp / max(int(y.sum()), 1)
    top = score.sort_values(ascending=False).index[:k]
    return {"precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0, "alerts": int(flag.sum()),
            "precision_at_k": round(float(y.loc[top].mean()), 3) if k else None,
            "pr_auc": round(float(average_precision_score(y, score)), 3) if 0 < y.sum() < len(y) else None}


# ---------------------------------------------------------------- main
def score_all(e, p2=None, label_source="none"):
    """e = entries with features; p2 = DataFrame(entry_id, p2_score) or None. Returns (scored, metrics)."""
    e = e.copy()
    cols = ml_features(e)
    y = e["is_anomaly"].astype(int)
    e["rules_score"], pts = rules_score(e)
    for k, v in unsupervised(e, cols).items():
        e[f"{k}_pct"] = v
    e["p2_score"] = e["entry_id"].map(p2.set_index("entry_id")["p2_score"]) if p2 is not None else np.nan
    p2_prob = (e["p2_score"] / 100) if p2 is not None else None
    e["rule_hits"] = [[label_of(f) for f in pts.columns if pts.at[i, f] > 0] for i in e.index]

    if y.sum() == 0:                                           # no labels: no supervised model
        e["xgb_proba"] = 0.0
        unsup = e["iforest_pct"]
        e["risk_score"] = _blend(e["rules_score"], None, signal(p2_prob, 0.5) if p2 is not None else None, unsup)
        e["shap_top"] = [[] for _ in e.index]
        metrics = {"label_source": "none", "models": {}, "by_type": [], "feature_importance": [], "eval_rows": 0,
                   "split": "No labels in this data: rules + unsupervised detectors" + (" + Person 2's model" if p2 is not None else ""),
                   "unsupervised_choice": "iforest", "weights": WEIGHTS, "rules": RULES}
    else:
        held_types = config.HELD_OUT_MARKINGS if label_source == "dataset" else config.HELD_OUT_INJECTED
        held = e["anomaly_type"].isin(held_types)
        cutoff_date = e["posting_date"].quantile(1 - config.TEST_SHARE)
        train = (e["posting_date"] < cutoff_date) & ~held
        evalr = ~train
        X = pd.concat([e[cols].astype(float).fillna(0), user_columns(e)], axis=1)
        cols_sup = list(X.columns)
        t_eval = 0.5
        if y[train].sum() >= 3:
            m_eval, t_eval = _xgb_fit_tuned(X[train], y[train], e.loc[train, "posting_date"])
            e.loc[evalr, "xgb_eval"] = m_eval.predict_proba(X[evalr])[:, 1]
        else:
            e.loc[evalr, "xgb_eval"] = 0.0
        m, t_final = _xgb_fit_tuned(X[~held], y[~held], e.loc[~held, "posting_date"])   # final model
        e["xgb_proba"] = m.predict_proba(X)[:, 1]
        shap = pd.DataFrame(m.get_booster().predict(xgb.DMatrix(X), pred_contribs=True)[:, :-1], columns=cols_sup, index=e.index)
        ucols = [c for c in cols_sup if c.startswith("user_") and c not in cols]
        shap[ucols] = shap[ucols].where(X[ucols].to_numpy() == 1, 0.0)   # "Entered by Bob" only on Bob's entries
        e["shap_top"] = [[{"feature": label_of(f), "shap": round(float(v), 3)} for f, v in shap.loc[i].nlargest(5).items() if v > 0.05]
                         for i in e.index]

        ye = y[evalr]
        k = max(int(ye.sum()), 1)
        ev = e.loc[evalr]
        # autoencoder kept only with a clear gain over Isolation Forest
        ap = {u: (average_precision_score(ye, ev[f"{u}_pct"]) if 0 < ye.sum() < len(ye) else 0) for u in ("iforest", "lof", "autoencoder")}
        choice = "autoencoder" if ap["autoencoder"] > ap["iforest"] + 0.02 else ("lof" if ap["lof"] > ap["iforest"] + 0.02 else "iforest")
        unsup = e[f"{choice}_pct"]
        e["risk_score"] = _blend(e["rules_score"], signal(e["xgb_proba"], t_final),
                                 signal(p2_prob, 0.5) if (p2 is not None and config.USE_PERSON2) else None, unsup)
        honest = _blend(ev["rules_score"], signal(ev["xgb_eval"], t_eval), None, ev[f"{choice}_pct"])
        layers = [("Rules", ev["rules_score"], CUT["rules"]), ("Isolation Forest", ev["iforest_pct"], CUT["pct"]),
                  ("LOF", ev["lof_pct"], CUT["pct"]), ("Autoencoder", ev["autoencoder_pct"], CUT["pct"]),
                  ("XGBoost (ours)", ev["xgb_eval"], t_eval), ("Risk score (combined)", honest, config.ALERT_CUTOFF)]
        models = {n: _metrics(ye, s, c, k) for n, s, c in layers}
        if p2 is not None:
            models["Person 2 model (in-sample here)"] = _metrics(ye, ev["p2_score"] / 100, CUT["proba"], k)
        by_type = []
        for t, s in ev[ye == 1].groupby("anomaly_type"):
            hs = honest.loc[s.index]
            by_type.append({"type": t, "n": int(len(s)), "held_out": t in held_types,
                            "rules": round(float((s["rules_score"] >= CUT["rules"]).mean()), 2),
                            "iforest": round(float((s["iforest_pct"] >= CUT["pct"]).mean()), 2),
                            "lof": round(float((s["lof_pct"] >= CUT["pct"]).mean()), 2),
                            "autoencoder": round(float((s["autoencoder_pct"] >= CUT["pct"]).mean()), 2),
                            "xgboost": round(float((s["xgb_eval"] >= t_eval).mean()), 2),
                            "person2": round(float((s["p2_score"] >= 50).mean()), 2) if p2 is not None else None,
                            "combined": round(float((hs >= config.ALERT_CUTOFF).mean()), 2)})
        imp = sorted(({"feature": label_of(f), "importance": round(float(v), 4)} for f, v in zip(cols_sup, m.feature_importances_)),
                     key=lambda d: -d["importance"])
        seen = (ye == 1) & ~ev["anomaly_type"].isin(held_types)
        recall_seen = {n: round(float((sc[seen] >= c).mean()), 3) if seen.any() else None
                       for n, sc, c in [("XGBoost (ours)", ev["xgb_eval"], t_eval), ("Risk score (combined)", honest, config.ALERT_CUTOFF)]}
        metrics = {"label_source": label_source, "models": models, "recall_seen_types": recall_seen, "by_type": by_type, "feature_importance": imp,
                   "eval_rows": int(evalr.sum()), "eval_positives": int(ye.sum()), "test_from": f"{cutoff_date:%Y-%m-%d}",
                   "held_out_types": held_types, "unsupervised_choice": choice,
                   "xgb_threshold": {"evaluation": round(t_eval, 3), "final": round(t_final, 3)},
                   "unsupervised_pr_auc": {k2: round(float(v), 3) for k2, v in ap.items()},
                   "split": f"Temporal split: trained before {cutoff_date:%d/%m/%Y}, tested after; "
                            f"{', '.join(held_types)} never shown to XGBoost",
                   "weights": WEIGHTS, "rules": RULES}
    e["alert"] = (e["risk_score"] >= config.ALERT_CUTOFF).astype(int)
    e["risk_level"] = np.where(e["risk_score"] >= 75, "High", np.where(e["risk_score"] >= config.ALERT_CUTOFF, "Medium", "Low"))
    e = e.drop(columns=[c for c in ["xgb_eval"] if c in e])
    return e.sort_values("risk_score", ascending=False).reset_index(drop=True), metrics
