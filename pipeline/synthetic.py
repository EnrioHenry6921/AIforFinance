"""
synthetic.py - Faker ledger generator (the "synthetic data" row of the project brief).

Writes a ledger in the SAME layout as the original DIB file (journal_entries_4203.csv):
posting_id, document_date, posting_date, entered_date, gl_account, gl_account_name, amount,
cd_flag, user, tax_rate, ref_id, text, label, marking, weekend, nwh, promptly, top_n, high_cash
with ~0.8% labelled anomalies using the DIB markings 1-8. It can also write a French FEC.

Uses: test fixture, stand-in when the real file is missing, and Person 1's generator.
    python -m pipeline.synthetic --entries 20000 --out data/raw/synthetic_dib.csv
    python -m pipeline.synthetic --format fec --out data/raw/synthetic_FEC.txt
"""
import argparse
import random

import numpy as np
import pandas as pd

from . import config

USERS = ["Alice", "Bob", "Charlie", "David", "Fred", "Max"]
SKR = {"1000": "Cash", "1100": "Bank (Postbank)", "1200": "Bank", "1210": "Bank (secondary)", "1400": "Trade receivables",
       "1576": "Input tax, 19%", "1600": "Trade payables", "1776": "VAT, 19%", "3400": "Purchase of goods, 19%",
       "4120": "Salaries", "4210": "Rent", "4600": "Advertising expenses", "4950": "Legal and consulting expenses",
       "8400": "Revenue, 19%", "1590": "Clearing account"}
PRODUCTS = ["Rake", "Spade", "Hedge trimmer", "Watering can", "Garden hose", "Lawn mower", "Pruning shears", "Wheelbarrow"]


def _lines(pid, pdate, edate, user, text, legs, ref=""):
    return [{"posting_id": pid, "document_date": pdate.strftime("%Y-%m-%d"), "posting_date": pdate.strftime("%Y-%m-%d"),
             "entered_date": edate.strftime("%Y-%m-%d %H:%M:%S"), "gl_account": a, "gl_account_name": SKR[a],
             "amount": round(amt, 2), "cd_flag": cd, "user": user, "tax_rate": 19 if a in ("1576", "1776") else 0,
             "ref_id": ref, "text": text} for a, amt, cd in legs]


def generate(entries=20000, years=(2023, 2024), anomaly_rate=0.008, seed=7):
    rng = np.random.default_rng(seed)
    random.seed(seed)
    days = pd.bdate_range(f"{years[0]}-01-02", f"{years[-1]}-12-30")
    rows, labels = [], {}
    n_anom = int(entries * anomaly_rate)
    anomalous = set(rng.choice(entries, n_anom, replace=False).tolist())
    for i in range(entries):
        pid = f"{'abcdefghi'[i % 9]}_{i}"
        d = pd.Timestamp(rng.choice(days))
        user = USERS[i % len(USERS)]
        ent = d + pd.Timedelta(days=int(rng.integers(0, 8)), hours=int(rng.integers(8, 17)), minutes=int(rng.integers(0, 60)))
        prod = random.choice(PRODUCTS)
        net = round(float(rng.lognormal(np.log(400), 0.8)), 2)
        kind = i % 4
        mark = 0
        if i in anomalous:
            mark = int(rng.integers(1, 9))
            if mark == 1:
                net = round(float(rng.uniform(20000, 60000)), 2)
            elif mark == 3:
                ent = d + pd.Timedelta(days=int(rng.integers(10, 30)), hours=10)
            elif mark == 4:
                ent = d + pd.Timedelta(days=int(rng.integers(30, 120)), hours=10)
            elif mark == 5:
                ent = d + pd.Timedelta(days=1, hours=int(random.choice([21, 22, 23, 2, 3])))
            elif mark == 6:
                d = d + pd.Timedelta(days=(5 - d.weekday()) % 7)        # move to Saturday
                ent = d + pd.Timedelta(days=2, hours=10)
        vat = round(net * 0.19, 2)
        if mark == 2:
            amt = round(float(rng.uniform(1500, 6000)), 2)
            legs, text = [("4950", amt, "D"), ("1000", amt, "C")], "Cash payment consulting"
        elif mark == 7:
            legs, text = [("1600", net, "D"), ("1210", net, "C")], f"Payment supplier {prod}"
        elif mark == 8:
            legs, text = [("1600", net, "D"), ("1400", net, "C")], f"Clearing {prod}"
        elif kind == 0:
            legs, text = [("3400", net, "D"), ("1576", vat, "D"), ("1600", net + vat, "C")], f"{prod} purchase"
        elif kind == 1:
            legs, text = [("1400", net + vat, "D"), ("8400", net, "C"), ("1776", vat, "C")], f"{prod} sale"
        elif kind == 2:
            legs, text = [("1600", net, "D"), ("1100", net, "C")], f"Payment supplier {prod}"
        else:
            legs, text = [("1100", net, "D"), ("1400", net, "C")], f"Customer payment {prod}"
        if i % 500 == 0:                                                  # monthly-like manual entries
            pid, legs, text = f"p_{i}", [("4210", 2500.0, "D"), ("1600", 2500.0, "C")], "Rent accrual"
        rows += _lines(pid, d, ent, user, text, legs)
        labels[pid] = mark
    df = pd.DataFrame(rows)
    df["marking"] = df["posting_id"].map(labels)
    df["label"] = (df["marking"] > 0).astype(int)
    pdts, edts = pd.to_datetime(df["posting_date"]), pd.to_datetime(df["entered_date"])
    df["weekend"] = (pdts.dt.weekday >= 5).astype(int)
    df["nwh"] = ((edts.dt.hour < 6) | (edts.dt.hour >= 20)).astype(int)
    df["promptly"] = ((edts.dt.normalize() - pdts).dt.days < 10).astype(int)
    df["top_n"] = (df["amount"] > df["amount"].quantile(0.999)).astype(int)
    df["high_cash"] = ((df["gl_account"] == "1000") & (df["amount"] > 1000)).astype(int)
    return df


def to_fec(df):
    """Convert the synthetic DIB layout into an 18-column French FEC (PCG accounts)."""
    pcg = {"1000": "530000", "1100": "512000", "1200": "512100", "1210": "512900", "1400": "411000", "1576": "445660",
           "1600": "401000", "1776": "445710", "3400": "607000", "4120": "641100", "4210": "613200", "4600": "623000",
           "4950": "622600", "8400": "706000", "1590": "471000"}
    jr = df["posting_id"].str.split("_").str[0].map(lambda p: "OD" if p in config.MANUAL_PREFIXES else "AC")
    d = pd.to_datetime(df["posting_date"]).dt.strftime("%Y%m%d")
    amt = df["amount"].map(lambda x: f"{x:.2f}".replace(".", ","))
    out = pd.DataFrame({
        "JournalCode": jr, "JournalLib": jr.map({"OD": "Opérations diverses", "AC": "Achats"}),
        "EcritureNum": df["posting_id"], "EcritureDate": d, "CompteNum": df["gl_account"].map(pcg),
        "CompteLib": df["gl_account_name"], "CompAuxNum": "", "CompAuxLib": "", "PieceRef": df["posting_id"],
        "PieceDate": d, "EcritureLib": df["text"], "Debit": amt.where(df["cd_flag"] == "D", "0,00"),
        "Credit": amt.where(df["cd_flag"] == "C", "0,00"), "EcritureLet": "", "DateLet": "",
        "ValidDate": pd.to_datetime(df["entered_date"]).dt.strftime("%Y%m%d"), "Montantdevise": "", "Idevise": "EUR",
    })
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", type=int, default=20000)
    ap.add_argument("--format", choices=["dib", "fec"], default="dib")
    ap.add_argument("--out", default=str(config.RAW_DIR / "synthetic_dib.csv"))
    a = ap.parse_args()
    df = generate(a.entries)
    if a.format == "fec":
        to_fec(df).to_csv(a.out, sep="\t", index=False)
    else:
        df.to_csv(a.out, index=False)
    print(f"{a.out}: {df['posting_id'].nunique():,} entries, {df.groupby('posting_id')['label'].max().sum()} labelled anomalies")
