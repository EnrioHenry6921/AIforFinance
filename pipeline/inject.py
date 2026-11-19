"""
inject.py - Add LABELLED anomalous entries to a ledger, so the demo can prove the system
finds them and we can measure recall / precision when the data has no labels of its own.
(With the original DIB file the dataset's own 850 labels are used instead; see run.py.)

Each type carries ONE pattern only, so we can see which model catches which pattern - and test
on types the ML never saw (circularity test). Works for SKR03 (DIB) and PCG (French FEC).

  P1 Timing : weekend_posting, holiday_posting, year_end_revenue, night_entry, late_entry
  P2 Amount : round_amount, split_below_threshold
  Context   : duplicate_manual (same manual entry booked twice by the same user)
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
    "split_below_threshold": ("P2 Amount", "Payment split into entries just under the approval limit"),
    "duplicate_manual":      ("Context",   "Same manual entry booked twice"),
}


def _odd(rng, lo, hi):
    a = round(float(rng.uniform(lo, hi)), 2)
    return a + 0.37 if a % 100 == 0 else a


def inject(lines, holidays, n=config.INJECT_N, seed=42, chart="SKR03", has_time=True):
    rng = np.random.default_rng(seed)
    random.seed(seed)
    acc = config.CHARTS[chart]["accounts"]
    vat_rate = config.CHARTS[chart]["vat_rate"]
    A = lambda k: acc[k][0]
    name = {v[0]: v[1] for v in acc.values()}
    start, end = lines["posting_date"].min(), lines["posting_date"].max()
    users = [u for u in lines["user"].unique() if u not in ("", "unknown")] or ["AUDIT_DEMO"]
    years = sorted(lines["posting_date"].dt.year.unique())
    span = max((end - start).days, 30)
    hol_days = [pd.Timestamp(d) for d in holidays if start <= pd.Timestamp(d) <= end and pd.Timestamp(d).weekday() < 5]

    def workday(margin=0):
        for _ in range(500):
            d = start + pd.Timedelta(days=int(rng.integers(0, max(span - margin, 1))))
            if d.weekday() < 5 and str(d.date()) not in holidays:
                return d.normalize()
        return start.normalize()

    def entered(p, days=None, hour=None):
        days = int(rng.integers(1, 6)) if days is None else days
        hour = int(rng.integers(9, 17)) if hour is None else hour
        t = p + pd.Timedelta(days=days, hours=hour if has_time else 0, minutes=int(rng.integers(0, 60)) if has_time else 0)
        while has_time and hour >= 9 and t.weekday() >= 5:
            t += pd.Timedelta(days=1)
        return t

    def entry(eid, p, ent, user, text, legs, kind):
        return [{"entry_id": eid, "posting_date": p, "document_date": p, "entered_at": ent, "account": a,
                 "account_name": name.get(a, a), "debit": d, "credit": c, "user": user, "text": text, "ref_id": "",
                 "source": "manual", "is_anomaly": 1, "anomaly_type": kind, "label_source": "injected"} for a, d, c in legs]

    kinds = [k for k in TYPES if has_time or k != "night_entry"]
    rows, k = [], 0
    manual = lines[lines["source"] == "manual"]
    for i in range(n):
        kind = kinds[i % len(kinds)]
        user = random.choice(users)
        k += 1
        eid = f"z_{k}"
        if kind == "weekend_posting":
            p = workday() + pd.Timedelta(days=0)
            p = p + pd.Timedelta(days=(5 - p.weekday()) % 7)
            a = _odd(rng, 1200, 3800)
            rows += entry(eid, p, entered(p), user, "Adjustment supplier account", [(A("payable"), a, 0.0), (A("bank"), 0.0, a)], kind)
        elif kind == "holiday_posting":
            p = random.choice(hol_days) if hol_days else workday()
            a = _odd(rng, 1200, 3800)
            rows += entry(eid, p, entered(p), user, "Adjustment miscellaneous expenses", [(A("maintenance"), a, 0.0), (A("other_liab"), 0.0, a)], kind)
        elif kind == "year_end_revenue":
            p = pd.Timestamp(random.choice(years), 12, 31)
            while p.weekday() >= 5:
                p -= pd.Timedelta(days=1)
            net = _odd(rng, 9000, 30000)
            vat = round(net * vat_rate, 2)
            rows += entry(eid, p, entered(p, days=int(rng.integers(3, 9))), user, "Additional revenue year end",
                          [(A("receivable"), net + vat, 0.0), (A("revenue"), 0.0, net), (A("vat_out"), 0.0, vat)], kind)
        elif kind == "night_entry":
            p = workday()
            a = _odd(rng, 1200, 3800)
            h = int(random.choice([21, 22, 23, 1, 2, 3]))
            rows += entry(eid, p, entered(p, days=1 if h < 6 else 0, hour=h), user, "Correction supplier balance",
                          [(A("payable"), a, 0.0), (A("bank"), 0.0, a)], kind)
        elif kind == "late_entry":
            p = workday(margin=160)
            a = _odd(rng, 1200, 3800)
            rows += entry(eid, p, entered(p, days=int(rng.integers(60, 150))), user, "Consulting fees",
                          [(A("consulting"), a, 0.0), (A("payable"), 0.0, a)], kind)
        elif kind == "round_amount":
            p = workday()
            a = float(random.choice([6000, 7500, 8000, 10000, 12500, 15000]))
            rows += entry(eid, p, entered(p), user, "Consulting fees", [(A("consulting"), a, 0.0), (A("bank"), 0.0, a)], kind)
        elif kind == "split_below_threshold":
            p = workday()
            low = config.APPROVAL_THRESHOLD * (1 - config.NEAR_THRESHOLD_BAND)
            for part in range(3):
                a = _odd(rng, low + 10, config.APPROVAL_THRESHOLD - 5)
                rows += entry(eid if part == 0 else f"z_{k}_{part}", p, entered(p), user, "Advertising campaign",
                              [(A("advertising"), a, 0.0), (A("bank"), 0.0, a)], kind)
        elif kind == "duplicate_manual":
            if len(manual):
                src = manual[manual["entry_id"] == random.choice(manual["entry_id"].unique())].copy()
                shift = pd.Timedelta(days=int(rng.integers(1, 4)))
                src["entry_id"], src["posting_date"], src["document_date"] = eid, src["posting_date"] + shift, src["document_date"] + shift
                src["entered_at"] = src["entered_at"] + shift
                src["is_anomaly"], src["anomaly_type"], src["label_source"] = 1, kind, "injected"
                rows += src.to_dict("records")
            else:
                p = workday()
                a = _odd(rng, 1200, 3800)
                for part in range(2):
                    rows += entry(eid if part == 0 else f"z_{k}_d", p + pd.Timedelta(days=part), entered(p), user,
                                  "Rent accrual", [(A("maintenance"), a, 0.0), (A("other_liab"), 0.0, a)], kind)
    out = pd.concat([lines, pd.DataFrame(rows)], ignore_index=True)
    out["label_source"] = out["label_source"].replace("", np.nan).fillna("injected" if lines["is_anomaly"].sum() == 0 else "mixed")
    return out
