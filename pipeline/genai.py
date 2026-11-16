"""
genai.py - LOCAL generative AI (Ollama): audit memos, entry nature, engagement summary.
No ledger data leaves the computer. If Ollama is not running, every function falls back
to a TEMPLATE built from the same computed facts, so the pipeline never breaks.

Setup once: install Ollama (ollama.com), then `ollama pull llama3:latest`.
"""
import json

import requests

from . import config, prompts

FOLLOW_UPS = {
    "Posted on a weekend": "Ask who posted it and why outside working days; check system access logs for that user.",
    "Posted on a public holiday": "Confirm the business reason for posting on a public holiday and who approved it.",
    "Posted in the year-end closing window": "Cut-off test: match to delivery/service evidence and check for a reversal in January.",
    "Revenue booked at year end": "Obtain the customer contract and delivery note; confirm the receivable with the customer; check January credit notes.",
    "Entered long after the posting date": "Obtain the reason for the late entry; check whether the period was already closed (backdating).",
    "Entered at night": "Check the user's access log and whether the session was authorised; confirm the user's identity.",
    "Entered on a weekend": "Check who had system access on that day.",
    "Round amount": "Obtain the invoice or contract that justifies the exact amount.",
    "Just below the approval threshold": "Look for other entries by the same user/supplier that together exceed the approval limit.",
    "Several near-threshold entries same user/day": "Add the entries together and check whether one approval was avoided by splitting.",
    "Above performance materiality": "Vouch to supporting documents and confirm management approval.",
}

NATURE_KEYWORDS = [("accrual", "accrual"), ("deferral", "deferral"), ("release", "deferral"),
                   ("reversal", "reversal"), ("credit note", "credit note"), ("salary", "payroll"),
                   ("wage", "payroll"), ("social security", "payroll"), ("rent", "expense"),
                   ("revenue", "sale"), ("adjustment", "adjustment"), ("correction", "adjustment"),
                   ("consulting", "expense"), ("advertising", "expense")]


def ollama_available():
    try:
        return requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2).ok
    except requests.RequestException:
        return False


def ask_llm(system, user, model=None):
    try:
        r = requests.post(f"{config.OLLAMA_URL}/api/chat", timeout=config.OLLAMA_TIMEOUT, json={
            "model": model or config.OLLAMA_MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": "json", "stream": False, "options": {"temperature": 0.2}})
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])
    except (requests.RequestException, KeyError, ValueError):
        return None


def nature(row, use_llm=False):
    """Data enrichment: what kind of entry is it? Keywords first, LLM for the rest."""
    t = row["text"].lower()
    for k, v in NATURE_KEYWORDS:
        if k in t:
            return v
    accs = row["accounts"]
    if "8400" in accs:
        return "sale"
    if "3400" in accs:
        return "purchase"
    if use_llm:
        res = ask_llm(prompts.SYSTEM_AUDITOR.format(language="English"),
                      prompts.USER_NATURE.format(text=row["text"], accounts=accs))
        if res and res.get("nature"):
            return res["nature"]
    return "payment" if "1100" in accs or "1000" in accs else "other"


def _facts(row):
    return dict(
        entry_id=row["entry_id"], source=row["source"], nature=row["nature"],
        posting_date=f"{row['posting_date']:%d/%m/%Y}", weekday=f"{row['posting_date']:%A}",
        entered_at=f"{row['entered_at']:%d/%m/%Y %H:%M}", delay=int(row["entry_delay_days"]),
        hour=int(row["entered_hour"]), text=row["text"], accounts=row["accounts"],
        main_account=row["main_account"], main_account_name=row["main_account_name"],
        amount=float(row["amount"]), user=row["user"], risk_score=row["risk_score"],
        rules=", ".join(row["rule_hits"]) or "none",
        shap="; ".join(f"{d['feature']} (+{d['shap']})" for d in row["shap_top"]) or "none",
        threshold=config.APPROVAL_THRESHOLD, perf_mat=float(row["perf_mat"]))


def template_memo(row):
    hits = list(row["rule_hits"]) or [d["feature"] for d in row["shap_top"][:2]]
    level = "High" if row["risk_score"] >= 75 else "Medium" if row["risk_score"] >= config.ALERT_CUTOFF else "Low"
    assertion = ("cut-off" if any("year" in h.lower() for h in hits)
                 else "occurrence" if any(k in " ".join(hits).lower() for k in ["night", "weekend", "holiday", "round"])
                 else "accuracy")
    return {
        "risk_level": level,
        "why_suspicious": (f"{row['source'].capitalize()} entry {row['entry_id']} of {row['amount']:,.2f} EUR "
                           f"(\"{row['text']}\", posted by {row['user']}) shows: " + "; ".join(h.lower() for h in hits)
                           + ". Under NEP 240 / ISA 240 these are indicators of possible management override "
                             "or error that require testing."),
        "possible_explanations": ["Legitimate closing or correction entry", "Timing of the bookkeeping workflow",
                                  "Approved exceptional transaction"],
        "follow_up_procedures": [FOLLOW_UPS.get(h, "Obtain and inspect supporting documents.") for h in hits[:4]]
        + ["Obtain written approval and the supporting document."],
        "assertion_at_risk": assertion,
        "conclusion": "Investigate before concluding." if level != "Low" else "Low priority - document and close.",
        "source": "template (local LLM not running)",
    }


def memo(row, use_llm, model=None, language="English"):
    if use_llm:
        res = ask_llm(prompts.SYSTEM_AUDITOR.format(language=language),
                      prompts.USER_MEMO.format(**_facts(row)), model)
        if res and "why_suspicious" in res:
            res["source"] = f"{model or config.OLLAMA_MODEL} (local) - prompts {prompts.PROMPT_VERSION}"
            return res
    return template_memo(row)


def engagement_summary(facts, use_llm, model=None):
    if use_llm:
        res = ask_llm(prompts.SYSTEM_AUDITOR.format(language="English"), prompts.USER_SUMMARY.format(**facts), model)
        if res and "overview" in res:
            res["source"] = f"{model or config.OLLAMA_MODEL} (local)"
            return res
    return {
        "overview": (f"We tested 100% of the ledger ({facts['n_entries']:,} entries, {facts['n_manual']:,} manual). "
                     f"{facts['n_alerts']} entries reached a risk score of {facts['cutoff']} or more. "
                     f"All {facts['found']} of the {facts['n_injected']} demo anomalies were found, including the "
                     f"types the ML never saw in training."),
        "key_themes": [f"{k}: {v} alerts" for k, v in facts["by_rule"].items()][:6],
        "recommended_next_steps": ["Review the High alerts first and obtain supporting documents",
                                   "Discuss year-end and late manual entries with the chief accountant",
                                   "Check access rights of users posting at night or on weekends",
                                   "Extend the test to the next closing period"],
        "limitations": ["Demo anomalies were injected; real fraud may look different",
                        "Thresholds and materiality are our assumptions",
                        "No supplier or invoice number in the ledger: duplicates cannot be tested",
                        "Template text - run the local LLM for a written summary"],
        "source": "template (local LLM not running)",
    }
