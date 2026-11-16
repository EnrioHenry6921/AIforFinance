"""
features.py - From ledger LINES to one row per ENTRY, with the features for our
two parameters (P1 Timing, P2 Amount) plus a few context columns.
"""
import numpy as np
import pandas as pd

from . import config

BENFORD = {d: np.log10(1 + 1 / d) for d in range(1, 10)}

# Features the models use, with plain-English names for the auditor
FEATURES = {
    # P1 Timing
    "is_weekend": "Posted on a weekend",
    "is_holiday": "Posted on a public holiday",
    "is_period_end": "Posted in the year-end closing window",
    "revenue_at_year_end": "Revenue booked at year end",
    "entry_delay_days": "Days between posting date and entry",
    "is_late_entry": "Entered long after the posting date",
    "is_night": "Entered at night",
    "entered_on_weekend": "Entered on a weekend",
    # P2 Amount
    "log_amount": "Size of the amount",
    "is_round": "Round amount",
    "near_threshold": "Just below the approval threshold",
    "split_group": "Several near-threshold entries same user/day",
    "above_perf_mat": "Above performance materiality",
    "amount_vs_account": "Unusual amount for this account",
    # Context
    "is_manual": "Manual entry",
}
PARAM = {f: "P1 Timing" for f in list(FEATURES)[:8]}
PARAM.update({f: "P2 Amount" for f in list(FEATURES)[8:14]})
PARAM.update({"is_manual": "Context"})


def build_entries(lines):
    lines = lines.copy()
    lines["amt"] = lines["debit"]
    g = lines.groupby("entry_id", sort=False)
    # main account = the line with the largest debit
    main = lines.loc[g["debit"].idxmax(), ["entry_id", "account", "account_name"]].set_index("entry_id")
    e = g.agg(
        posting_date=("posting_date", "first"), entered_at=("entered_at", "first"),
        user=("user", "first"), text=("text", "first"), source=("source", "first"),
        amount=("debit", "sum"), credit=("credit", "sum"), n_lines=("debit", "size"),
        accounts=("account", lambda s: " / ".join(sorted(set(s)))),
        is_anomaly=("is_anomaly", "max"), anomaly_type=("anomaly_type", "first"),
    )
    e = e.join(main.rename(columns={"account": "main_account", "account_name": "main_account_name"}))
    return e.reset_index()


def add_features(e, holidays):
    e = e.copy()
    pd_ = e["posting_date"]
    # ---- P1 Timing ----
    e["is_weekend"] = (pd_.dt.weekday >= 5).astype(int)
    e["is_holiday"] = pd_.dt.strftime("%Y-%m-%d").isin(set(holidays)).astype(int)
    ye = pd.to_datetime(pd_.dt.year.astype(str) + "-12-31")
    to_close = (ye - pd_).dt.days                     # days before 31/12
    after_open = (pd_ - (ye - pd.offsets.YearBegin(1))).dt.days   # days after 1/1
    e["days_to_close"] = np.minimum(to_close, after_open + 1)
    e["is_period_end"] = (to_close <= config.PERIOD_END_DAYS).astype(int)
    e["revenue_at_year_end"] = (e["is_period_end"].astype(bool)
                                & e["accounts"].str.contains("8400")).astype(int)
    e["entry_delay_days"] = (e["entered_at"].dt.normalize() - pd_).dt.days.clip(lower=0)
    e["is_late_entry"] = (e["entry_delay_days"] > config.LATE_ENTRY_DAYS).astype(int)
    h = e["entered_at"].dt.hour
    e["entered_hour"] = h
    e["is_night"] = ((h >= config.NIGHT_HOURS[0]) | (h < config.NIGHT_HOURS[1])).astype(int)
    e["entered_on_weekend"] = (e["entered_at"].dt.weekday >= 5).astype(int)

    # ---- P2 Amount ----
    a = e["amount"]
    e["log_amount"] = np.log1p(a)
    e["is_round"] = ((a >= 1000) & (np.isclose(a % config.ROUND_UNIT, 0))).astype(int)
    low = config.APPROVAL_THRESHOLD * (1 - config.NEAR_THRESHOLD_BAND)
    e["near_threshold"] = a.between(low, config.APPROVAL_THRESHOLD, inclusive="left").astype(int)
    grp = e[e["near_threshold"] == 1].groupby(["user", e["posting_date"].dt.date])["entry_id"].transform("count")
    e["split_group"] = 0
    e.loc[grp.index, "split_group"] = (grp >= 2).astype(int)

    years = e["posting_date"].dt.year
    revenue = e[e["main_account"].eq("1400") | e["accounts"].str.contains("8400")].groupby(years)["amount"].sum() / 1.19
    perf_mat = (revenue * config.MATERIALITY_PCT_REVENUE * config.PERFORMANCE_MAT_PCT)
    e["perf_mat"] = years.map(perf_mat).fillna(perf_mat.mean() if len(perf_mat) else 1e12)
    e["above_perf_mat"] = (a >= e["perf_mat"]).astype(int)
    # how unusual is the amount for its main account (robust z-score on log amount)
    med = e.groupby("main_account")["log_amount"].transform("median")
    mad = e.groupby("main_account")["log_amount"].transform(lambda s: (s - s.median()).abs().median()) + 0.1
    e["amount_vs_account"] = ((e["log_amount"] - med) / mad).clip(-10, 10).round(2)
    e["first_digit"] = a.map(lambda x: int(f"{x:e}"[0]) if x >= 1 else 0)

    # ---- Context ----
    e["is_manual"] = (e["source"] == "manual").astype(int)
    # recurring = same account + same amount in 6+ different months (rent, salaries): expected, less risky
    months = e.groupby(["main_account", e["amount"].round(2)])["posting_date"].transform(
        lambda s: s.dt.to_period("M").nunique())
    e["is_recurring"] = ((months >= 6) & (e["is_manual"] == 1)).astype(int)
    return e, perf_mat.round(0).to_dict()


def benford_table(e):
    """Observed vs expected first digits, overall and per user (MAD = mean absolute deviation)."""
    fd = e[e["first_digit"] > 0]
    obs = fd["first_digit"].value_counts(normalize=True).reindex(range(1, 10)).fillna(0)
    overall = [{"digit": d, "observed": round(float(obs[d]), 4), "benford": round(BENFORD[d], 4)} for d in range(1, 10)]
    users = []
    for u, s in fd.groupby("user"):
        o = s["first_digit"].value_counts(normalize=True).reindex(range(1, 10)).fillna(0)
        mad = float(np.mean([abs(o[d] - BENFORD[d]) for d in range(1, 10)]))
        users.append({"user": u, "entries": int(len(s)), "mad": round(mad, 4),
                      "conformity": "close" if mad < 0.006 else "acceptable" if mad < 0.012
                      else "marginal" if mad < 0.015 else "nonconformity"})
    mad_all = float(np.mean([abs(obs[d] - BENFORD[d]) for d in range(1, 10)]))
    return {"overall": overall, "mad": round(mad_all, 4), "by_user": users}
