"""
features.py - From ledger LINES to one row per ENTRY, with the features for our
two parameters (P1 Timing, P2 Amount) plus context signals from the project brief
(user profiles, account age, unusual account combinations, duplicates, cash).

Teammates can add their own features: any column named feat_<something> in a file
data/external/features*.csv (entry_id + feat_ columns) is merged and used by the ML.
"""
import numpy as np
import pandas as pd

from . import config

BENFORD = {d: np.log10(1 + 1 / d) for d in range(1, 10)}

# Features, plain-English names for the auditor, and which parameter they belong to
FEATURES = {
    # P1 Timing
    "is_weekend": ("Posted on a weekend", "P1 Timing"),
    "is_holiday": ("Posted on a public holiday", "P1 Timing"),
    "is_period_end": ("Posted in the year-end closing window", "P1 Timing"),
    "revenue_at_year_end": ("Revenue booked at year end", "P1 Timing"),
    "entry_delay_days": ("Days between posting date and entry", "P1 Timing"),
    "is_delayed_entry": ("Entered 10-29 days after the posting date", "P1 Timing"),
    "is_late_entry": ("Entered long after the posting date", "P1 Timing"),
    "is_night": ("Entered outside working hours", "P1 Timing"),
    "entered_on_weekend": ("Entered on a weekend", "P1 Timing"),
    # P2 Amount
    "log_amount": ("Size of the amount", "P2 Amount"),
    "is_round": ("Round amount", "P2 Amount"),
    "near_threshold": ("Just below the approval threshold", "P2 Amount"),
    "split_group": ("Several near-threshold entries same user/day", "P2 Amount"),
    "above_perf_mat": ("Above performance materiality", "P2 Amount"),
    "amount_vs_account": ("Unusual amount for this account", "P2 Amount"),
    "high_cash": ("High cash disbursement", "P2 Amount"),
    # Context (brief: user profiles, account age, unusual account combinations, duplicates)
    "rare_account_combo": ("Rare combination of accounts", "Context"),
    "new_account": ("Account used for the first time recently", "Context"),
    "user_unusual_hour": ("Unusual entry hour for this user", "Context"),
    "possible_duplicate": ("Same entry booked twice", "Context"),
    "n_lines": ("Number of lines in the entry", "Context"),
    "is_manual": ("Manual entry", "Context"),
}
LABEL = {k: v[0] for k, v in FEATURES.items()}
PARAM = {k: v[1] for k, v in FEATURES.items()}


def _prefix(accounts, prefixes):
    return accounts.str.split(" / ").map(lambda accs: any(a.startswith(tuple(prefixes)) for a in accs))


def build_entries(lines):
    g = lines.groupby("entry_id", sort=False)
    main = lines.loc[g["debit"].idxmax(), ["entry_id", "account", "account_name"]].set_index("entry_id")
    e = g.agg(
        posting_date=("posting_date", "first"), document_date=("document_date", "first"),
        entered_at=("entered_at", "first"), user=("user", "first"), text=("text", "first"),
        source=("source", "first"), amount=("debit", "sum"), credit=("credit", "sum"), n_lines=("debit", "size"),
        accounts=("account", lambda s: " / ".join(sorted(set(s.astype(str))))),
        is_anomaly=("is_anomaly", "max"), anomaly_type=("anomaly_type", lambda s: next((x for x in s if x), "")),
    )
    e = e.join(main.rename(columns={"account": "main_account", "account_name": "main_account_name"}))
    e["amount"] = np.maximum(e["amount"], e["credit"])          # entry value counted once (like Person 2)
    return e.reset_index()


def working_hours(h):
    """The ledger's own working day: the first and last hour that each hold at least WORK_HOUR_SHARE of entries.
    Falls back to config.NIGHT_HOURS when the data has no clear working day (e.g. all entries at 00:00)."""
    share = h.value_counts(normalize=True)
    busy = sorted(share[share >= config.WORK_HOUR_SHARE].index)
    if len(busy) < 4:
        return config.NIGHT_HOURS[1], config.NIGHT_HOURS[0] - 1
    return int(busy[0]), int(busy[-1])


def outside_working_hours(h):
    start, end = working_hours(h)
    return (h < start) | (h > end)


def add_features(e, holidays, chart="SKR03", has_time=True, lines=None, external=None):
    e = e.copy()
    ch = config.CHARTS[chart]
    pd_ = e["posting_date"]
    # ---- P1 Timing ----
    e["is_weekend"] = (pd_.dt.weekday >= 5).astype(int)
    e["is_holiday"] = pd_.dt.strftime("%Y-%m-%d").isin(set(holidays)).astype(int)
    ye = pd.to_datetime(pd_.dt.year.astype(str) + "-12-31")
    to_close = (ye - pd_).dt.days
    e["days_to_close"] = to_close
    e["is_period_end"] = (to_close <= config.PERIOD_END_DAYS).astype(int)
    e["is_revenue"] = _prefix(e["accounts"], ch["revenue_prefixes"]).astype(int)
    e["revenue_at_year_end"] = (e["is_period_end"].astype(bool) & e["is_revenue"].astype(bool)).astype(int)
    e["entry_delay_days"] = (e["entered_at"].dt.normalize() - pd_).dt.days.clip(lower=0).fillna(0)
    e["is_delayed_entry"] = e["entry_delay_days"].between(config.DELAYED_ENTRY_DAYS, config.LATE_ENTRY_DAYS - 1).astype(int)
    e["is_late_entry"] = (e["entry_delay_days"] >= config.LATE_ENTRY_DAYS).astype(int)
    e["entered_on_weekend"] = (e["entered_at"].dt.weekday >= 5).astype(int)
    if has_time:
        h = e["entered_at"].dt.hour
        e["entered_hour"] = h
        e["is_night"] = outside_working_hours(h).astype(int)
        lo = e.groupby("user")["entered_hour"].transform(lambda s: s.quantile(config.USER_HOUR_PCT[0]))
        hi = e.groupby("user")["entered_hour"].transform(lambda s: s.quantile(config.USER_HOUR_PCT[1]))
        e["user_unusual_hour"] = ((h < lo) | (h > hi)).astype(int)
    else:                                              # FEC etc.: no entry time -> these checks are off
        e["entered_hour"] = np.nan
        e["is_night"] = 0
        e["user_unusual_hour"] = 0

    # ---- P2 Amount ----
    a = e["amount"]
    e["log_amount"] = np.log1p(a)
    e["is_round"] = ((a >= 1000) & np.isclose(a % config.ROUND_UNIT, 0)).astype(int)
    low = config.APPROVAL_THRESHOLD * (1 - config.NEAR_THRESHOLD_BAND)
    e["near_threshold"] = a.between(low, config.APPROVAL_THRESHOLD, inclusive="left").astype(int)
    grp = e[e["near_threshold"] == 1].groupby(["user", e["posting_date"].dt.date])["entry_id"].transform("count")
    e["split_group"] = 0
    e.loc[grp.index, "split_group"] = (grp >= 2).astype(int)

    # materiality from REVENUE LINES of the chart in use (works for SKR03 and PCG)
    years = e["posting_date"].dt.year
    if lines is not None:
        rev_l = lines[lines["account"].str.startswith(tuple(ch["revenue_prefixes"]))]
        revenue = (rev_l["credit"] - rev_l["debit"]).groupby(rev_l["posting_date"].dt.year).sum()
    else:
        revenue = e[e["is_revenue"] == 1].groupby(years)["amount"].sum() / (1 + ch["vat_rate"])
    revenue = revenue[revenue > 0]
    perf_mat = (revenue * config.MATERIALITY_PCT_REVENUE * config.PERFORMANCE_MAT_PCT).round(0)
    fallback = float(perf_mat.mean()) if len(perf_mat) else float(e["amount"].quantile(0.999))
    e["perf_mat"] = years.map(perf_mat).fillna(fallback)
    e["above_perf_mat"] = (a >= e["perf_mat"]).astype(int)
    med = e.groupby("main_account")["log_amount"].transform("median")
    mad = e.groupby("main_account")["log_amount"].transform(lambda s: (s - s.median()).abs().median()) + 0.1
    e["amount_vs_account"] = ((e["log_amount"] - med) / mad).clip(-10, 10).round(2)
    e["first_digit"] = a.map(lambda x: int(f"{x:e}"[0]) if x >= 1 else 0)
    is_cash = _prefix(e["accounts"], ch["cash_prefixes"])
    e["high_cash"] = (is_cash & (a >= config.HIGH_CASH_AMOUNT)).astype(int)

    # ---- Context ----
    e["is_manual"] = (e["source"] == "manual").astype(int)
    combo_n = e.groupby("accounts")["entry_id"].transform("count")
    e["rare_account_combo"] = (combo_n <= config.RARE_COMBO_MAX).astype(int)
    if lines is not None:
        first = lines.groupby("account")["posting_date"].min()
        uses = lines.groupby("account")["entry_id"].nunique()
        acc_list = e["accounts"].str.split(" / ")
        start = e["posting_date"].min()
        def is_new(row_accs, d):
            return any((d - first[a]).days < config.NEW_ACCOUNT_DAYS and (first[a] - start).days > config.NEW_ACCOUNT_DAYS
                       and uses[a] <= 20 for a in row_accs if a in first.index)
        e["new_account"] = [int(is_new(accs, d)) for accs, d in zip(acc_list, e["posting_date"])]
        e["account_age_days"] = [min(((d - first[x]).days for x in accs if x in first.index), default=0)
                                 for accs, d in zip(acc_list, e["posting_date"])]
    else:
        e["new_account"], e["account_age_days"] = 0, 0
    key = e["user"] + "|" + e["accounts"] + "|" + e["amount"].round(2).astype(str) + "|" + e["text"]
    order = e.sort_values("posting_date")
    gap_prev = order.groupby(key.loc[order.index])["posting_date"].diff().dt.days
    gap_next = order.groupby(key.loc[order.index])["posting_date"].diff(-1).dt.days.abs()
    dup = ((gap_prev <= config.DUPLICATE_DAYS) | (gap_next <= config.DUPLICATE_DAYS)).reindex(e.index).fillna(False)
    e["possible_duplicate"] = (dup & (e["is_manual"] == 1)).astype(int)        # products have fixed prices: system entries repeat
    months = e.groupby(["main_account", e["amount"].round(2)])["posting_date"].transform(lambda s: s.dt.to_period("M").nunique())
    e["is_recurring"] = ((months >= 6) & (e["is_manual"] == 1)).astype(int)

    # ---- Teammates' extra features (feat_*) ----
    if external is not None and len(external):
        ext = external.set_index("entry_id")
        for c in [c for c in ext.columns if c.startswith("feat_")]:
            e[c] = pd.to_numeric(e["entry_id"].map(ext[c]), errors="coerce").fillna(0)
    return e, {int(k): float(v) for k, v in perf_mat.items()}


def ml_features(e):
    """Columns given to the ML models (labels and is_manual excluded: they would leak the answer)."""
    base = [f for f in FEATURES if f != "is_manual"]
    return base + [c for c in e.columns if c.startswith("feat_")]


def user_columns(e, min_share=0.005):
    """One 0/1 column per regular user, for the supervised model only. Labelled anomalies are often tied to a
    person (in the DIB ledger every weekend anomaly was entered by one user); this lifted XGBoost's
    PR-AUC on the temporal test from 0.25 to 0.62. Rare users are pooled in 'other'."""
    share = e["user"].value_counts(normalize=True)
    keep = share[share >= min_share].index
    u = e["user"].where(e["user"].isin(keep), "other")
    if u.nunique() < 2:
        return pd.DataFrame(index=e.index)
    return pd.get_dummies(u, prefix="user").astype(float)


def label_of(f):
    if f.startswith("user_") and f not in LABEL:
        return f"Entered by {f[5:]}"
    return LABEL.get(f, f.replace("feat_", "").replace("_", " ").capitalize())


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
    mad_all = float(np.mean([abs(obs[d] - BENFORD[d]) for d in range(1, 10)])) if len(fd) else 0.0
    return {"overall": overall, "mad": round(mad_all, 4), "by_user": users}
