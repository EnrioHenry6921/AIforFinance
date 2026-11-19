"""
loader.py - Read any general ledger into ONE standard format (one row = one posting line).

Supported inputs (detected automatically):
  1. DIB General Ledger, original Zenodo file (amount + cd_flag, with label + marking ground truth)
  2. DIB General Ledger, our team's cleaned file (debit/credit columns, no labels)
  3. French FEC (18 columns, .txt tab/pipe separated, French decimals, dates YYYYMMDD)
  4. Any other CSV/Excel: columns are matched by name (like Person 2's _find_col), or with a
     mapping file:  python -m pipeline.run --input my.csv --map mapping.json
     mapping.json = {"entry_id": "JE_number", "posting_date": "Date", "account": "GL", ...}

Labels: kept if present (DIB label/marking, or is_anomaly/anomaly_type from a teammate).
They are used ONLY to evaluate, never as model inputs.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .textclean import clean_text

STD = ["entry_id", "posting_date", "document_date", "entered_at", "account", "account_name",
       "debit", "credit", "user", "text", "ref_id", "source"]
LABELS = ["is_anomaly", "anomaly_type", "label_source"]

# name candidates for generic files (first match wins, case-insensitive)
CANDIDATES = {
    "entry_id": ["entry_id", "posting_id", "journal_entry_id", "je_number", "document_id", "ecriturenum", "belegnr"],
    "posting_date": ["posting_date", "ecrituredate", "date", "gl_date", "buchungsdatum"],
    "document_date": ["document_date", "piecedate", "doc_date", "belegdatum"],
    "entered_at": ["entered_at", "entered_date", "entry_date", "created_at", "timestamp", "validdate", "erfassungsdatum"],
    "account": ["account", "gl_account", "comptenum", "account_number", "account_id", "konto"],
    "account_name": ["account_name", "gl_account_name", "comptelib", "account_description"],
    "debit": ["debit", "debit_amount", "amount_debit", "soll"],
    "credit": ["credit", "credit_amount", "amount_credit", "haben"],
    "amount": ["amount", "amount_lc", "local_amount", "transaction_amount", "betrag"],
    "cd_flag": ["cd_flag", "dc_flag", "debit_credit", "sh_kennzeichen"],
    "user": ["user", "user_id", "created_by", "username", "benutzer"],
    "text": ["text", "description", "ecriturelib", "line_text", "buchungstext"],
    "ref_id": ["ref_id", "reference", "document_number", "invoice_number", "pieceref"],
    "is_anomaly": ["is_anomaly", "label", "anomaly", "fraud_label"],
    "anomaly_type": ["anomaly_type", "marking", "scenario"],
}


def _num(s):
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float).fillna(0.0)
    return pd.to_numeric(s.astype(str).str.replace(" ", "").str.replace(" ", "").str.replace(",", "."),
                         errors="coerce").fillna(0.0)


def _date(s):
    s = s.astype(str).str.strip()
    d = pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    rest = d.isna()
    if rest.any():
        d[rest] = pd.to_datetime(s[rest], errors="coerce", format="mixed")
    return d


def _find(cols, names):
    low = {c.lower().strip(): c for c in cols}
    return next((low[n] for n in names if n in low), None)


def _labels(df, n):
    """Ground truth if the file has it: DIB label/marking, or a teammate's is_anomaly/anomaly_type."""
    lab = _find(df.columns, CANDIDATES["is_anomaly"])
    typ = _find(df.columns, CANDIDATES["anomaly_type"])
    if lab is None and typ is None:
        return pd.Series(0, index=df.index), pd.Series("", index=df.index), ""
    def truthy(v):
        s = str(v).strip().lower()
        return 0 if s in {"", "0", "0.0", "false", "normal", "none", "no", "nan"} else 1
    is_a = df[lab].map(truthy) if lab else df[typ].map(truthy)
    if typ:
        def name(v):
            try:
                code = int(float(v))
                return f"M{code} {config.DIB_MARKINGS[code]}" if code in config.DIB_MARKINGS else ""
            except (TypeError, ValueError):
                s = str(v).strip()
                return "" if s.lower() in {"", "nan", "none", "0"} else s
        kind = df[typ].map(name)
    else:
        kind = pd.Series("", index=df.index)
    kind = kind.where(is_a == 1, "")
    source = "dataset" if (typ and str(typ).lower() == "marking") or (lab and str(lab).lower() == "label") else "provided"
    return is_a.astype(int), kind, source


def from_dib(df):
    if "debit" not in df.columns:                     # original Zenodo file: amount + cd_flag (D/C)
        amt = _num(df["amount"])
        cd = df["cd_flag"].astype(str).str.upper().str.strip()
        df = df.assign(debit=amt.where(cd == "D", 0.0), credit=amt.where(cd == "C", 0.0))
    doc = df["document_date"] if "document_date" in df.columns else df["posting_date"]
    ref = df["ref_id"] if "ref_id" in df.columns else pd.Series("", index=df.index)
    out = pd.DataFrame({
        "entry_id": df["posting_id"].astype(str),
        "posting_date": _date(df["posting_date"]).dt.normalize(),
        "document_date": _date(doc).dt.normalize(),
        "entered_at": _date(df["entered_date"]),
        "account": df["gl_account"].astype(str).str.replace(r"\.0$", "", regex=True),
        "account_name": df.get("gl_account_name", pd.Series("", index=df.index)).astype(str),
        "debit": _num(df["debit"]), "credit": _num(df["credit"]),
        "user": df["user"].astype(str), "text": df["text"].astype(str),
        "ref_id": ref.astype(str).replace({"0": "", "nan": "", "0.0": ""}),
    })
    out["source"] = out["entry_id"].str.split("_").str[0].isin(config.MANUAL_PREFIXES).map({True: "manual", False: "system"})
    return out


def from_fec(df):
    out = pd.DataFrame({
        "entry_id": df["JournalCode"].astype(str) + "_" + df["EcritureNum"].astype(str),
        "posting_date": _date(df["EcritureDate"]),
        "document_date": _date(df["PieceDate"]).fillna(_date(df["EcritureDate"])),
        "entered_at": _date(df["ValidDate"]).fillna(_date(df["EcritureDate"])),   # FEC: validation DATE, no time
        "account": df["CompteNum"].astype(str), "account_name": df["CompteLib"].astype(str),
        "debit": _num(df["Debit"]), "credit": _num(df["Credit"]),
        "user": df["user_id"].astype(str) if "user_id" in df.columns else pd.Series("unknown", index=df.index),
        "text": df["EcritureLib"].astype(str), "ref_id": df["PieceRef"].astype(str),
    })
    out["source"] = df["JournalCode"].isin(config.MANUAL_JOURNALS).map({True: "manual", False: "system"})
    return out


def from_generic(df, mapping=None):
    cols = {k: (mapping or {}).get(k) or _find(df.columns, v) for k, v in CANDIDATES.items()}
    missing = [k for k in ("entry_id", "posting_date", "account") if not cols[k]]
    if missing:
        raise ValueError(f"Cannot find column(s) {missing}. Columns in the file: {list(df.columns)}. "
                         "Write a mapping file, e.g. {\"entry_id\": \"JE_no\"}, and pass --map mapping.json")
    if cols["debit"] and cols["credit"]:
        debit, credit = _num(df[cols["debit"]]), _num(df[cols["credit"]])
    elif cols["amount"] and cols["cd_flag"]:
        amt, cd = _num(df[cols["amount"]]), df[cols["cd_flag"]].astype(str).str.upper().str[0]
        debit, credit = amt.where(cd.isin(["D", "S"]), 0.0), amt.where(cd.isin(["C", "H"]), 0.0)
    elif cols["amount"]:                                  # signed amounts: + debit, - credit
        amt = _num(df[cols["amount"]])
        debit, credit = amt.clip(lower=0), (-amt).clip(lower=0)
    else:
        raise ValueError("No amount columns found (debit/credit, amount + debit/credit flag, or signed amount).")
    get = lambda k, default="": df[cols[k]] if cols[k] else pd.Series(default, index=df.index)
    pdate = _date(df[cols["posting_date"]])
    out = pd.DataFrame({
        "entry_id": df[cols["entry_id"]].astype(str), "posting_date": pdate.dt.normalize(),
        "document_date": _date(get("document_date")).fillna(pdate).dt.normalize(),
        "entered_at": _date(get("entered_at")).fillna(pdate),
        "account": df[cols["account"]].astype(str), "account_name": get("account_name").astype(str),
        "debit": debit, "credit": credit, "user": get("user", "unknown").astype(str),
        "text": get("text").astype(str), "ref_id": get("ref_id").astype(str),
    })
    src = mapping.get("source") if mapping else None
    if src and src in df.columns:
        out["source"] = df[src].astype(str).str.lower().map(lambda v: "manual" if v in {"manual", "1", "true", "od"} else "system")
    else:
        out["source"] = out["entry_id"].str.split("_").str[0].isin(config.MANUAL_PREFIXES).map({True: "manual", False: "system"})
    return out


def resolve_input(path=None):
    """The ledger to use: the given path, else the first known file in data/raw/, else any CSV there."""
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"{p} does not exist")
        return p
    for name in config.RAW_FALLBACKS:
        if (config.RAW_DIR / name).exists():
            return config.RAW_DIR / name
    found = sorted(list(config.RAW_DIR.glob("*.csv")) + list(config.RAW_DIR.glob("*.txt")) + list(config.RAW_DIR.glob("*.xlsx")))
    if not found:
        raise FileNotFoundError(f"No ledger in {config.RAW_DIR}. Put journal_entries_4203.csv there "
                                "(https://zenodo.org/records/22014653) or run: python -m pipeline.synthetic")
    return found[0]


def detect_sep(path):
    """Separator from the header line: the original DIB file uses ';', FEC uses tab or '|'."""
    with open(path, encoding="utf-8", errors="replace") as f:
        head = f.readline()
    return max([";", ",", "\t", "|"], key=head.count)


def read_any(path):
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str)
    sep = detect_sep(path)
    dtype = str if path.suffix.lower() == ".txt" else None
    return pd.read_csv(path, sep=sep, dtype=dtype, low_memory=False, encoding_errors="replace")


def load(path=None, mapping=None, chart=None):
    """Return (lines, meta). meta: format, chart, has_entry_time, label_source, file."""
    path = resolve_input(path)
    raw = read_any(path)
    raw.columns = [str(c).strip() for c in raw.columns]
    if isinstance(mapping, (str, Path)):
        mapping = json.loads(Path(mapping).read_text())
    if mapping:
        lines, fmt = from_generic(raw, mapping), "Mapped file"
    elif "posting_id" in raw.columns and "gl_account" in raw.columns:
        lines, fmt = from_dib(raw), "DIB general ledger" + (" (original, labelled)" if "marking" in raw.columns else "")
    elif "EcritureNum" in raw.columns:
        lines, fmt = from_fec(raw), "French FEC"
    else:
        lines, fmt = from_generic(raw), "Generic ledger"
    lines["is_anomaly"], lines["anomaly_type"], label_source = _labels(raw, len(raw))
    lines["label_source"] = label_source
    lines["text"] = clean_text(lines["text"])
    lines = lines[lines["entry_id"].ne("") & lines["entry_id"].ne("nan")]

    if chart is None:
        chart = "PCG" if fmt == "French FEC" or lines["account"].str.match(r"^(411|401|512|70\d)").mean() > 0.2 else "SKR03"
    has_time = bool(((lines["entered_at"].dt.hour + lines["entered_at"].dt.minute) > 0).mean() > 0.05)
    meta = {"format": fmt, "chart": chart, "has_entry_time": has_time, "label_source": label_source,
            "file": path.name, "leaky_columns_ignored": [c for c in config.DIB_LEAKY_COLUMNS if c in raw.columns]}
    return lines[STD + LABELS].reset_index(drop=True), meta


def datacard(lines, meta):
    """Short description of the dataset (Data slide + website)."""
    e = lines.groupby("entry_id").agg(d=("debit", "sum"), c=("credit", "sum"), src=("source", "first"),
                                      lab=("is_anomaly", "max"))
    return {
        "format": meta["format"], "file": meta["file"], "chart_of_accounts": meta["chart"],
        "lines": int(len(lines)), "entries": int(len(e)),
        "manual_entries": int((e["src"] == "manual").sum()),
        "period": f"{lines['posting_date'].min():%d/%m/%Y} - {lines['posting_date'].max():%d/%m/%Y}",
        "users": int(lines["user"].nunique()), "accounts": int(lines["account"].nunique()),
        "unbalanced_entries": int(((e["d"] - e["c"]).abs() > 0.01).sum()),
        "missing_values": int(lines[["posting_date", "account"]].isna().sum().sum()),
        "entered_before_posting": int((lines["entered_at"].dt.normalize() < lines["document_date"]).sum()),
        "has_entry_time": meta["has_entry_time"],
        "labelled_entries": int(e["lab"].sum()), "label_source": meta["label_source"] or "none",
    }
