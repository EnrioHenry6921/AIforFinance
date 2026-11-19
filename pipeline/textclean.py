"""
textclean.py - Clean entry descriptions (brief: "Gen AI - data: cleaning of entry descriptions").

Step 1 (always, deterministic): trim, collapse spaces, drop placeholder values, fix ALL-CAPS.
Step 2 (optional, local LLM): genai.nature() classifies what the entry is (accrual, reversal...).
The cleaned text is what the memos and the website show; the original stays in the source file.
"""
import re

import pandas as pd

PLACEHOLDERS = {"nan", "none", "null", "n/a", "na", "-", "--", "?", "0"}


def clean_one(s):
    s = re.sub(r"\s+", " ", str(s)).strip().strip(";,.-_ ")
    if s.lower() in PLACEHOLDERS:
        return ""
    if len(s) > 3 and s.isupper():
        s = s.capitalize()
    return s


def clean_text(series):
    uniq = pd.Series(series.unique())
    mapping = dict(zip(uniq, uniq.map(clean_one)))      # clean each distinct text once (fast on 250k lines)
    return series.map(mapping).fillna("")
