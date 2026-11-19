"""Deterministic audit recommendation engine for JournalGuard AI.

Accepts a dict, pandas Series, or mapping-like journal-entry record. Supports
Person 2's DIB output (posting_id/risk_score/entry_amount) and the French demo
app's output (entry_id/risk_score/amount/risk_reasons).
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

LIBRARY_PATH = Path(__file__).with_name("recommendation_library.csv")


def _value(entry, *names, default=None):
    for name in names:
        try:
            value = entry.get(name, None)
        except AttributeError:
            try: value = entry[name]
            except Exception: value = None
        if value is not None and not pd.isna(value) and str(value).strip() not in ("", "nan", "None"):
            return value
    return default


def _truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _as_float(value, default=0.0):
    try: return float(value)
    except (TypeError, ValueError): return default


def _load_library():
    if not LIBRARY_PATH.exists():
        raise FileNotFoundError(f"Recommendation library not found: {LIBRARY_PATH}")
    return pd.read_csv(LIBRARY_PATH).fillna("")


def _signals(entry):
    """Return only observations supported by explicit fields in the input."""
    signals=[]
    if _truthy(_value(entry, "is_weekend_calc", "is_weekend", default=False)):
        signals.append((6, "The posting date falls on a weekend according to the supplied date indicator."))
    if _truthy(_value(entry, "is_unusual_hour_calc", "is_unusual_time", default=False)):
        signals.append((5, "The supplied time indicator classifies the posting/entry time as outside the configured normal-hours window."))
    delay=_as_float(_value(entry, "post_to_enter_days", "entry_delay_days", default=None), default=float('nan'))
    if delay == delay and delay > 29:
        signals.append((4, f"The entry was recorded {delay:g} day(s) after the posting date, based on supplied date fields."))
    elif delay == delay and 10 <= delay <= 29:
        signals.append((3, f"The entry was recorded {delay:g} day(s) after the posting date, based on supplied date fields."))
    amount=_as_float(_value(entry, "entry_amount", "amount", "total_debit", default=0))
    # No arbitrary 'high amount' threshold: only use explicit flag if the upstream system supplies it.
    if _truthy(_value(entry, "high_amount_flag", "is_high_amount", default=False)):
        signals.append((1, "The upstream analysis explicitly flagged the amount as high; the threshold and comparison population should be verified."))
    if _truthy(_value(entry, "high_cash_flag", "is_high_cash", default=False)):
        signals.append((2, "The upstream analysis explicitly flagged a high cash disbursement; the cash classification should be verified."))
    # An explicit marking/anomaly type is accepted only if supplied by caller; do not infer it from score.
    explicit=_value(entry, "anomaly_type", "marking", default=None)
    if explicit is not None:
        try:
            code=int(float(explicit))
            if 1 <= code <= 8 and not any(c==code for c,_ in signals):
                signals.append((code, f"The input record explicitly identifies DIB marking code {code}; verify this is a trusted audit/test label, not a live model feature."))
        except (TypeError, ValueError):
            pass
    return signals, amount


def get_audit_recommendation(entry):
    """Return a structured, deterministic, evidence-limited recommendation."""
    score=_as_float(_value(entry,"risk_score","xgb_anomaly_score","anomaly_score",default=0))
    level=str(_value(entry,"risk_level",default=("High" if score>=70 else "Medium" if score>=40 else "Low"))).title()
    entry_id=_value(entry,"posting_id","entry_id","id",default="Not supplied")
    date=_value(entry,"posting_date","date",default="Not supplied")
    amount=_as_float(_value(entry,"entry_amount","amount","total_debit",default=0))
    accounts=_value(entry,"account_names","accounts","account_signature",default="Not supplied")
    signals, _ = _signals(entry)
    library=_load_library()
    selected=[]
    for code, explanation in signals:
        rows=library[library["marking_code"].astype(str)==str(code)]
        if len(rows):
            row=rows.iloc[0]
            selected.append({"code":code,"anomaly":row["anomaly"],"explanation":explanation,
                "potential_risk":row["potential_risk"],"evidence_to_request":row["evidence_to_request"],
                "audit_procedure":row["audit_procedure"],"scope_note":row["scope_note"]})
    if not selected:
        selected=[{"code":"GEN-0","anomaly":"Model-prioritised entry; specific driver not identified",
            "explanation":"The upstream model assigned a screening score, but the supplied fields do not identify a single supported anomaly type.",
            "potential_risk":"The entry may warrant further review due to its model score. The score alone does not establish an error, irregularity or fraud.",
            "evidence_to_request":"Obtain the source invoice/contract, purchase order where applicable, evidence of delivery or service, payment evidence, approval trail and relevant correspondence.",
            "audit_procedure":"Agree the entry to source documentation; verify business purpose, authorisation, amount, accounting period, account coding and settlement; compare with similar entries and investigate inconsistencies.",
            "scope_note":"General follow-up only. Do not attribute the score to a particular feature unless the model explanation or source data supports that attribution."}]
    return {"entry_id":str(entry_id),"posting_date":str(date),"amount":amount,"accounts":str(accounts),
        "risk_score":round(score,1),"risk_level":level,
        "score_caveat":"A screening/prioritisation score learned from the supplied model and synthetic labelled scenarios; it is not a probability of fraud or proof of misconduct.",
        "signals":selected,"priority":"High" if level=="High" else "Normal follow-up" if level=="Medium" else "Routine / sample-based review"}


def get_audit_recommendations(scored_df):
    """Apply the recommendation engine to each row of a scored DataFrame."""
    return [get_audit_recommendation(row) for _,row in scored_df.iterrows()]
