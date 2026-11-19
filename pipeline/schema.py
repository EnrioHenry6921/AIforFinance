"""
schema.py - Checks run on every ledger BEFORE scoring, so bad input fails loudly and clearly
instead of producing wrong results. Errors stop the run; warnings are reported in the datacard.
"""
import pandas as pd


class LedgerError(ValueError):
    pass


def validate(lines, meta):
    errors, warnings = [], []
    if lines.empty:
        errors.append("The file has no posting lines.")
        raise LedgerError("; ".join(errors))
    bad_dates = lines["posting_date"].isna().mean()
    if bad_dates > 0.01:
        errors.append(f"{bad_dates:.0%} of posting dates could not be read (expected YYYY-MM-DD or YYYYMMDD).")
    elif bad_dates > 0:
        warnings.append(f"{lines['posting_date'].isna().sum()} lines without a readable posting date were dropped.")
    if (lines["debit"] < 0).any() or (lines["credit"] < 0).any():
        warnings.append("Negative debit/credit amounts found; they were kept as signed values.")
    if (lines["debit"] + lines["credit"]).eq(0).mean() > 0.5:
        errors.append("More than half of the lines have no amount: check the amount / debit / credit columns.")
    e = lines.groupby("entry_id")[["debit", "credit"]].sum()
    unbalanced = int(((e["debit"] - e["credit"]).abs() > 0.01).sum())
    if unbalanced:
        warnings.append(f"{unbalanced} entries do not balance (debit ≠ credit): they are scored and flagged.")
    sizes = lines.groupby("entry_id").size()
    if (sizes == 1).mean() > 0.5:
        warnings.append("Most entries have a single line: the entry id column may be wrong (one id per line?).")
    if not meta.get("has_entry_time"):
        warnings.append("No entry time in this file (e.g. FEC): night/working-hours checks are switched off.")
    if lines["user"].nunique() <= 1:
        warnings.append("No user information: user-based checks are switched off.")
    if meta.get("leaky_columns_ignored"):
        warnings.append("Generator flag columns ignored as model inputs: " + ", ".join(meta["leaky_columns_ignored"]))
    if errors:
        raise LedgerError(" ".join(errors))
    return lines[lines["posting_date"].notna()].copy(), warnings
