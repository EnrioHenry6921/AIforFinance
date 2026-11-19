"""
recommend.py - Person 3's audit recommendation library, connected to our red flags.

Person 3 delivered recommendation_library.csv: for each DIB marking (1-8) and five generic
cases (GEN-1..5) the potential risk, evidence to request, audit procedure and a scope note.
Their engine only uses signals that are explicitly supported by the data. We keep that
principle: each rule our pipeline triggered is mapped to ONE library code, and only those
codes are used. Labels (marking) are never used here: they would reveal the answer.
"""
from functools import lru_cache

import pandas as pd

from . import config

# our red flag (plain label) -> Person 3 library code
FLAG_TO_CODE = {
    "Above performance materiality": "1", "Size of the amount": "1", "Round amount": "1",
    "High cash disbursement": "2",
    "Entered 10-29 days after the posting date": "3",
    "Entered long after the posting date": "4",
    "Entered at night": "5", "Entered outside working hours": "5", "Unusual entry hour for this user": "GEN-3",
    "Posted on a weekend": "6", "Entered on a weekend": "6",
    "Same entry booked twice": "GEN-1",
    "Rare combination of accounts": "GEN-2", "Account used for the first time recently": "GEN-2",
    "Just below the approval threshold": "GEN-5", "Several near-threshold entries same user/day": "GEN-5",
    "Revenue booked at year end": "GEN-5", "Posted in the year-end closing window": "GEN-5",
    "Posted on a public holiday": "6", "Unusual amount for this account": "1",
}
GENERIC = {"code": "GEN-0", "anomaly": "Model-prioritised entry; specific driver not identified",
           "potential_risk": "The entry may warrant further review due to its model score. The score alone does not establish an error, irregularity or fraud.",
           "evidence_to_request": "Obtain the source invoice/contract, evidence of delivery or service, payment evidence, approval trail and relevant correspondence.",
           "audit_procedure": "Agree the entry to source documentation; verify business purpose, authorisation, amount, accounting period, account coding and settlement.",
           "scope_note": "General follow-up only. Do not attribute the score to a particular feature unless the model explanation supports it."}
SCORE_CAVEAT = ("A screening/prioritisation score, learned from labelled scenarios in a synthetic ledger; "
                "it is not a probability of fraud or proof of misconduct.")


@lru_cache(maxsize=1)
def library():
    if not config.PERSON3_LIBRARY.exists():
        return {}
    lib = pd.read_csv(config.PERSON3_LIBRARY, dtype=str).fillna("")
    return {r["marking_code"]: r.to_dict() for _, r in lib.iterrows()}


def recommend(rule_hits, shap_top=()):
    """Library entries supported by the red flags of ONE entry (deduplicated, in flag order)."""
    lib = library()
    out, seen = [], set()
    for flag in list(rule_hits) + [d["feature"] for d in shap_top]:
        code = FLAG_TO_CODE.get(flag)
        if code and code not in seen and code in lib:
            seen.add(code)
            r = lib[code]
            out.append({"code": code, "anomaly": r["anomaly"], "signal": flag, "potential_risk": r["potential_risk"],
                        "evidence_to_request": r["evidence_to_request"], "audit_procedure": r["audit_procedure"],
                        "scope_note": r["scope_note"]})
    return out or [{**GENERIC, "signal": "model score"}]
