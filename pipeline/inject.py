"""
inject.py - Add LABELLED anomalous entries to a clean ledger, so the demo can prove
the system finds them and we can measure recall / precision.

Each type carries ONE pattern only (everything else looks normal), so we can see
which model catches which pattern - and test on types the ML never saw (circularity).

  P1 Timing : weekend_posting, holiday_posting, year_end_revenue, night_entry, late_entry
  P2 Amount : round_amount, split_below_threshold
  (Duplicate payments were dropped: the ledger has no supplier or invoice number to test them.)
"""
import random

import numpy as np
import pandas as pd

from . import config

TYPES = {
    "weekend_posting":       ("P1 Timing", "Manual adjustment posted on a weekend"),
    "holiday_posting":       ("P1 Timing", "Manual adjustment posted on a public holiday"),
    "year_end_revenue":      ("P1 Timing", "Revenue booked on the last days of the year, entered in January"),
    "night_entry":           ("P1 Timing", "Entry typed in late at night"),
    "late_entry":            ("P1 Timing", "Entry typed in months after its posting date (backdating)"),
    "round_amount":          ("P2 Amount", "Large round amount with no invoice"),
    "split_below_threshold": ("P2 Amount", "Payment split into several entries just under the approval limit"),
}

ACC = {  # SKR03 accounts that exist in the DIB ledger
    "1100": "Bank (Postbank)", "1400": "Trade receivables", "1600": "Trade payables",
    "1700": "Other liabilities", "4950": "Legal and consulting expenses", "4260": "Maintenance of operating premises",
    "4600": "Advertising expenses", "8400": "Revenue, 19%", "1776": "VAT, 19%",
}


def _workday(rng, start, end, hol):
    while True:
        d = start + pd.Timedelta(days=int(rng.integers(0, (end - start).days)))
        if d.weekday() < 5 and str(d.date()) not in hol:
            return d


def _entered(rng, posting, days=None, hour=None):
    days = int(rng.integers(1, 8)) if days is None else days
    hour = int(rng.integers(9, 17)) if hour is None else hour
    t = posting.normalize() + pd.Timedelta(days=days, hours=hour, minutes=int(rng.integers(0, 60)))
    while days is not None and t.weekday() >= 5 and hour >= 9:   # keep entry time on a working day
        t += pd.Timedelta(days=1)
    return t


def _odd(rng, lo, hi):
    """A non-round amount (so only the intended pattern is present)."""
    a = round(float(rng.uniform(lo, hi)), 2)
    return a + 0.37 if a % 100 == 0 else a


def _entry(eid, posting, entered, user, text, legs, kind):
    return [{
        "entry_id": eid, "posting_date": posting.normalize(), "document_date": posting.normalize(),
        "entered_at": entered, "account": a, "account_name": ACC.get(a, a), "debit": d, "credit": c,
        "user": user, "text": text, "ref_id": "", "source": "manual", "is_anomaly": 1, "anomaly_type": kind,
    } for a, d, c in legs]


def inject(lines, holidays, n=config.INJECT_N, seed=42):
    rng = np.random.default_rng(seed)
    random.seed(seed)
    lines = lines.copy()
    start, end = lines["posting_date"].min(), lines["posting_date"].max()
    users = lines["user"].unique().tolist()
    years = sorted(lines["posting_date"].dt.year.unique())
    hol_days = [pd.Timestamp(d) for d in holidays if start <= pd.Timestamp(d) <= end and pd.Timestamp(d).weekday() < 5]

    rows, k = [], 0
    kinds = list(TYPES)
    for i in range(n):
        kind = kinds[i % len(kinds)]
        user = random.choice(users)
        k += 1
        eid = f"z_{k}"
        if kind == "weekend_posting":
            p = start + pd.Timedelta(days=int(rng.integers(0, (end - start).days)))
            while p.weekday() < 5:
                p += pd.Timedelta(days=1)
            a = _odd(rng, 1200, 3800)
            rows += _entry(eid, p, _entered(rng, p), user, "Adjustment supplier account",
                           [("1600", a, 0.0), ("1100", 0.0, a)], kind)
        elif kind == "holiday_posting":
            p = random.choice(hol_days) if hol_days else _workday(rng, start, end, holidays)
            a = _odd(rng, 1200, 3800)
            rows += _entry(eid, p, _entered(rng, p), user, "Adjustment miscellaneous expenses",
                           [("4260", a, 0.0), ("1700", 0.0, a)], kind)
        elif kind == "year_end_revenue":
            y = random.choice(years)
            p = pd.Timestamp(y, 12, 31)
            while p.weekday() >= 5:
                p -= pd.Timedelta(days=1)
            net = _odd(rng, 9000, 30000)
            vat = round(net * 0.19, 2)
            rows += _entry(eid, p, _entered(rng, p, days=int(rng.integers(3, 12))), user,
                           "Additional revenue year end", [("1400", net + vat, 0.0), ("8400", 0.0, net),
                                                           ("1776", 0.0, vat)], kind)
        elif kind == "night_entry":
            p = _workday(rng, start, end, holidays)
            a = _odd(rng, 1200, 3800)
            h = int(random.choice([21, 22, 23, 1, 2, 3]))
            rows += _entry(eid, p, _entered(rng, p, days=1 if h < 6 else 0, hour=h), user,
                           "Correction supplier balance", [("1600", a, 0.0), ("1100", 0.0, a)], kind)
        elif kind == "late_entry":
            p = _workday(rng, start, end - pd.Timedelta(days=160), holidays)
            a = _odd(rng, 1200, 3800)
            rows += _entry(eid, p, _entered(rng, p, days=int(rng.integers(60, 150))), user,
                           "Consulting fees", [("4950", a, 0.0), ("1600", 0.0, a)], kind)
        elif kind == "round_amount":
            p = _workday(rng, start, end, holidays)
            a = float(random.choice([6000, 7500, 8000, 10000, 12500, 15000]))
            rows += _entry(eid, p, _entered(rng, p), user, "Consulting fees",
                           [("4950", a, 0.0), ("1100", 0.0, a)], kind)
        elif kind == "split_below_threshold":
            p = _workday(rng, start, end, holidays)
            low = config.APPROVAL_THRESHOLD * (1 - config.NEAR_THRESHOLD_BAND)
            for part in range(3):                         # 3 entries, same user, same day
                a = _odd(rng, low + 10, config.APPROVAL_THRESHOLD - 5)
                pid = eid if part == 0 else f"z_{k}_{part}"
                rows += _entry(pid, p, _entered(rng, p), user, "Advertising campaign",
                               [("4600", a, 0.0), ("1100", 0.0, a)], kind)

    add = pd.DataFrame(rows)
    return pd.concat([lines, add], ignore_index=True)
