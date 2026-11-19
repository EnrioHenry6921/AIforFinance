"""
forecast.py - Predictive analytics (plan option B): expected monthly revenue vs actual.
Expected = same month last year x running growth of the year so far; months outside the band
are flagged. Works for any chart of accounts (revenue prefixes in config.CHARTS).
"""
import numpy as np
import pandas as pd

from . import config

DEFAULT_BAND = 0.25   # until three earlier months give a measured error


def forecast_revenue(lines, chart="SKR03"):
    pref = tuple(config.CHARTS[chart]["revenue_prefixes"])
    rev_l = lines[lines["account"].str.startswith(pref)]
    if rev_l.empty:
        return {"history": [], "months": [], "note": "No revenue accounts found for this chart of accounts."}
    rev = (rev_l["credit"] - rev_l["debit"]).groupby(rev_l["posting_date"].dt.to_period("M")).sum()
    rev.index = rev.index.to_timestamp()
    years = sorted(rev.index.year.unique())
    if len(years) < 2:
        return {"history": [{"month": t.strftime("%Y-%m"), "actual": round(float(v), 2)} for t, v in rev.items()],
                "months": [], "note": "Needs at least two years of history to forecast."}
    out, errors = [], []
    for t, actual in rev[rev.index.year > years[0]].items():
        ly = rev.get(pd.Timestamp(t.year - 1, t.month, 1))
        if ly is None or ly <= 0:
            continue                                                  # no comparable month: no forecast (never NaN)
        # growth so far this year, on matching months only (a month counts only if last year has it too)
        now = rev[(rev.index.year == t.year) & (rev.index < t)]
        prev = pd.Series({m: rev.get(pd.Timestamp(t.year - 1, m.month, 1)) for m in now.index}, dtype=float)
        ok = prev.notna() & (prev > 0)
        growth = float(now[ok].sum() / prev[ok].sum()) if ok.any() and prev[ok].sum() > 0 else 1.0
        exp = float(ly) * growth
        # the band uses only the errors of EARLIER months: no information from the future
        band = max(0.10, 2 * float(np.std(errors))) if len(errors) >= 3 else DEFAULT_BAND
        out.append({"month": t.strftime("%Y-%m"), "actual": round(float(actual), 2), "expected": round(exp, 2),
                    "low": round(exp * (1 - band), 2), "high": round(exp * (1 + band), 2),
                    "band_pct": round(band * 100, 1), "growth": round(growth, 3),
                    "flag": bool(actual > exp * (1 + band) or actual < exp * (1 - band))})
        if exp > 0 and actual > 0:
            errors.append(float(np.log(actual / exp)))
    hist = [{"month": t.strftime("%Y-%m"), "actual": round(float(v), 2)} for t, v in rev.items() if t.year == years[0]]
    return {"history": hist, "months": out, "band_pct": out[-1]["band_pct"] if out else None,
            "method": "Seasonal naive (same month last year) x year-to-date growth on matching months; "
                      "band = 2 x std of the log errors of earlier months only (±25% until 3 months are known)"}
