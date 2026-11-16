"""
loader.py - Read a general ledger into ONE standard format (one row = one line).

Supported inputs:
  1. DIB General Ledger Data (Zenodo 10.5281/zenodo.22014653) - columns posting_id, posting_date,
     entered_date, gl_account, debit, credit, user, text ...
  2. A French FEC (18 columns: JournalCode, EcritureNum, EcritureDate, CompteNum, Debit, Credit ...)

Standard columns: entry_id, posting_date, document_date, entered_at, account, account_name,
                  debit, credit, user, text, ref_id, source
"""
import pandas as pd

from . import config

STD = ["entry_id", "posting_date", "document_date", "entered_at", "account", "account_name",
       "debit", "credit", "user", "text", "ref_id", "source"]


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(" ", "").str.replace(" ", "")
                         .str.replace(",", "."), errors="coerce").fillna(0.0)


def from_dib(df):
    if "debit" not in df.columns:          # original Zenodo file: amount + cd_flag (D/C)
        amt = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        df = df.assign(debit=amt.where(df["cd_flag"] == "D", 0.0), credit=amt.where(df["cd_flag"] == "C", 0.0))
    df = df.assign(ref_id=df["ref_id"] if "ref_id" in df.columns else "",
                   document_date=df["document_date"] if "document_date" in df.columns else df["posting_date"])
    out = pd.DataFrame({
        "entry_id": df["posting_id"].astype(str),
        "posting_date": pd.to_datetime(df["posting_date"]),
        "document_date": pd.to_datetime(df["document_date"]),
        "entered_at": pd.to_datetime(df["entered_date"]),
        "account": df["gl_account"].astype(str),
        "account_name": df["gl_account_name"].astype(str),
        "debit": df["debit"].astype(float),
        "credit": df["credit"].astype(float),
        "user": df["user"].astype(str),
        "text": df["text"].astype(str),
        "ref_id": df["ref_id"].astype(str).replace("0", ""),
    })
    pfx = out["entry_id"].str.split("_").str[0]
    out["source"] = pfx.isin(config.MANUAL_PREFIXES).map({True: "manual", False: "system"})
    return out


def from_fec(df):
    d = lambda c: pd.to_datetime(df[c].astype(str), format="%Y%m%d", errors="coerce")
    out = pd.DataFrame({
        "entry_id": df["JournalCode"].astype(str) + "_" + df["EcritureNum"].astype(str),
        "posting_date": d("EcritureDate"),
        "document_date": d("PieceDate"),
        "entered_at": d("ValidDate"),               # FEC has no entry time: validation date
        "account": df["CompteNum"].astype(str),
        "account_name": df["CompteLib"].astype(str),
        "debit": _num(df["Debit"]),
        "credit": _num(df["Credit"]),
        "user": df.get("user_id", pd.Series([""] * len(df))).astype(str),
        "text": df["EcritureLib"].astype(str),
        "ref_id": df["PieceRef"].astype(str),
    })
    out["source"] = df["JournalCode"].isin(["OD", "AN"]).map({True: "manual", False: "system"})
    return out


def load(path=config.RAW_FILE):
    """Read the ledger; if the default file is missing, fall back to any CSV in data/raw/."""
    from pathlib import Path
    path = Path(path)
    if not path.exists():
        found = sorted(config.RAW_FILE.parent.glob("*.csv"))
        if not found:
            raise FileNotFoundError(f"No ledger found. Put the CSV in {config.RAW_FILE.parent} "
                                    "(download: https://zenodo.org/records/22014653)")
        path = found[0]
    raw = pd.read_csv(path, sep=None, engine="python", dtype=str) if str(path).endswith(".txt") \
        else pd.read_csv(path, low_memory=False)
    if "posting_id" in raw.columns:
        lines = from_dib(raw)
        fmt = "DIB general ledger"
    elif "EcritureNum" in raw.columns:
        lines = from_fec(raw)
        fmt = "French FEC"
    else:
        raise ValueError("Unknown ledger format: expected DIB (posting_id...) or FEC (EcritureNum...)")
    lines["is_anomaly"] = 0
    lines["anomaly_type"] = ""
    return lines[STD + ["is_anomaly", "anomaly_type"]], fmt


def datacard(lines, fmt):
    """Short description of the dataset (Data slide + website)."""
    e = lines.groupby("entry_id").agg(d=("debit", "sum"), c=("credit", "sum"), src=("source", "first"))
    return {
        "format": fmt,
        "lines": int(len(lines)),
        "entries": int(len(e)),
        "manual_entries": int((e["src"] == "manual").sum()),
        "period": f"{lines['posting_date'].min():%d/%m/%Y} - {lines['posting_date'].max():%d/%m/%Y}",
        "users": int(lines["user"].nunique()),
        "accounts": int(lines["account"].nunique()),
        "unbalanced_entries": int(((e["d"] - e["c"]).abs() > 0.01).sum()),
        "missing_values": int(lines[["posting_date", "account", "debit", "credit"]].isna().sum().sum()),
        "entered_before_posting": int((lines["entered_at"].dt.normalize() < lines["document_date"]).sum()),
    }
