"""
forecast.py - Predictive analytics (plan option B): expected monthly revenue vs actual.
Expected = same month last year x running growth of the year so far; months outside the band
are flagged. Works for any chart of accounts (revenue prefixes in config.CHARTS).
"""
import numpy as np
import pandas as pd

from . import config


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
    out, ratios = [], []
    for t, actual in rev[rev.index.year > years[0]].items():
        ly = rev.get(pd.Timestamp(t.year - 1, t.month, 1))
        if ly is None or ly <= 0:
            continue                                                  # no comparable month: no forecast (never NaN)
        ytd_now = rev[(rev.index.year == t.year) & (rev.index < t)]
        ytd_ly = rev[(rev.index.year == t.year - 1) & rev.index.month.isin(ytd_now.index.month)]
        growth = float(ytd_now.sum() / ytd_ly.sum()) if len(ytd_now) and ytd_ly.sum() > 0 else 1.0
        exp = float(ly) * growth
        ratios.append(actual / exp if exp else 1.0)
        out.append({"month": t.strftime("%Y-%m"), "actual": round(float(actual), 2), "expected": round(exp, 2)})
    sd = float(np.std(np.log(np.clip(ratios, 1e-6, None)))) if ratios else 0.1
    band = max(0.10, 2 * sd)
    for o in out:
        o["low"], o["high"] = round(o["expected"] * (1 - band), 2), round(o["expected"] * (1 + band), 2)
        o["flag"] = bool(o["actual"] > o["high"] or o["actual"] < o["low"])
    hist = [{"month": t.strftime("%Y-%m"), "actual": round(float(v), 2)} for t, v in rev.items() if t.year == years[0]]
    return {"history": hist, "months": out, "band_pct": round(band * 100, 1),
            "method": "Seasonal naive (same month last year) x running year-to-date growth; band = 2 x std of log errors"}
