"""
genai.py - LOCAL generative AI (Ollama): memos, entry nature, alert themes, engagement summary,
and questions about the alerts. No ledger data leaves the computer.

Every function works WITHOUT an LLM: the memo is then built from Person 3's recommendation
library (deterministic, evidence-limited); the LLM, when running, only rewrites it in better prose.
Setup once: install Ollama (ollama.com), then `ollama pull llama3`.
"""
import json
from collections import Counter

import pandas as pd
import requests

from . import config, prompts
from .recommend import SCORE_CAVEAT, recommend

NATURE_KEYWORDS = [("accrual", "accrual"), ("deferral", "deferral"), ("release", "deferral"), ("reversal", "reversal"),
                   ("credit note", "credit note"), ("salar", "payroll"), ("wage", "payroll"), ("social security", "payroll"),
                   ("rent", "expense"), ("utilities", "expense"), ("revenue", "sale"), ("adjustment", "adjustment"),
                   ("correction", "adjustment"), ("consulting", "expense"), ("advertising", "expense"), ("clearing", "clearing")]


def ollama_available():
    try:
        return requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2).ok
    except requests.RequestException:
        return False


def ask_llm(system, user, model=None):
    try:
        r = requests.post(f"{config.OLLAMA_URL}/api/chat", timeout=config.OLLAMA_TIMEOUT, json={
            "model": model or config.OLLAMA_MODEL, "format": "json", "stream": False, "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])
    except (requests.RequestException, KeyError, ValueError):
        return None


def nature(row, chart="SKR03", use_llm=False, model=None):
    """Data enrichment: what kind of entry is it? Keywords and accounts first, the LLM only for the rest."""
    t = str(row["text"]).lower()
    for k, v in NATURE_KEYWORDS:
        if k in t:
            return v
    accs = str(row["accounts"])
    ch = config.CHARTS[chart]
    if any(a.startswith(tuple(ch["revenue_prefixes"])) for a in accs.split(" / ")):
        return "sale"
    if any(a.startswith(("3400", "60")) for a in accs.split(" / ")):
        return "purchase"
    if use_llm:
        res = ask_llm(prompts.SYSTEM_AUDITOR.format(language="English"), prompts.USER_NATURE.format(text=row["text"], accounts=accs), model)
        if res and res.get("nature"):
            return str(res["nature"])
    return "payment" if any(a.startswith(tuple(ch["bank_prefixes"] + ch["cash_prefixes"])) for a in accs.split(" / ")) else "other"


def theme(row):
    """Group alerts by theme (brief: 'grouping of alerts by theme')."""
    hits = list(row["rule_hits"])
    if not hits:
        return "Flagged by the models only"
    from .features import FEATURES, LABEL
    inv = {v: k for k, v in LABEL.items()}
    params = [FEATURES[inv[h]][1] for h in hits if h in inv]
    top = Counter(params).most_common(1)[0][0] if params else "Other"
    return {"P1 Timing": "Timing (when it was posted or entered)", "P2 Amount": "Amount (size, round, threshold, cash)",
            "Context": "Context (accounts, user, duplicates)"}.get(top, top)


def _facts(row, recs):
    lib = "\n".join(f"- [{r['code']}] {r['anomaly']} (signal: {r['signal']}): risk: {r['potential_risk']} | evidence: "
                    f"{r['evidence_to_request']} | procedure: {r['audit_procedure']}" for r in recs)
    hour = row.get("entered_hour")
    return dict(
        entry_id=row["entry_id"], source=row["source"], nature=row.get("nature", ""),
        posting_date=f"{row['posting_date']:%d/%m/%Y}", weekday=f"{row['posting_date']:%A}",
        entered_at=f"{row['entered_at']:%d/%m/%Y %H:%M}", delay=int(row["entry_delay_days"]),
        hour_text=f", at {int(hour)}:00" if pd.notna(hour) else "", text=row["text"], accounts=row["accounts"],
        main_account=row["main_account"], main_account_name=row["main_account_name"], amount=float(row["amount"]),
        user=row["user"], risk_score=row["risk_score"], risk_level=row.get("risk_level", ""),
        rules=", ".join(row["rule_hits"]) or "none",
        shap="; ".join(f"{d['feature']} (+{d['shap']})" for d in row["shap_top"]) or "not available",
        p2=f"{row['p2_score']:.1f}/100" if pd.notna(row.get("p2_score")) else "not applicable",
        library=lib, threshold=config.APPROVAL_THRESHOLD, perf_mat=float(row["perf_mat"]))


def template_memo(row, recs):
    """Deterministic memo (Person 3's approach): only library procedures supported by the indicators."""
    hits = list(row["rule_hits"])
    level = row.get("risk_level") or ("High" if row["risk_score"] >= 75 else "Medium" if row["risk_score"] >= config.ALERT_CUTOFF else "Low")
    if hits:
        why = (f"{row['source'].capitalize()} entry {row['entry_id']} of {row['amount']:,.2f} EUR (\"{row['text']}\", posted by "
               f"{row['user']}) shows these indicators: " + "; ".join(h.lower() for h in hits) +
               ". They call for testing under NEP 240 / ISA 240; they are not evidence of an error or of fraud.")
    else:
        drivers = [d["feature"].lower() for d in row["shap_top"]][:3]
        why = (f"Entry {row['entry_id']} of {row['amount']:,.2f} EUR was prioritised by the models (score {row['risk_score']}/100) "
               "although no audit rule fired" + (": the model's main drivers are " + "; ".join(drivers) if drivers else "") +
               ". This resembles labelled anomalies; it is not evidence of an error or of fraud.")
    names = " ".join(hits).lower()
    assertion = ("cut-off" if any(w in names for w in ("year", "entered", "delay")) else
                 "occurrence" if any(w in names for w in ("weekend", "night", "holiday", "twice", "hour")) else
                 "accuracy" if any(w in names for w in ("amount", "round", "threshold", "materiality", "cash")) else "occurrence")
    return {
        "risk_level": level, "why_suspicious": why,
        "possible_explanations": ["Legitimate closing, correction or exceptional transaction", "Timing of the bookkeeping workflow"],
        "evidence_to_obtain": [r["evidence_to_request"] for r in recs][:4],
        "follow_up_procedures": [r["audit_procedure"] for r in recs][:4],
        "assertion_at_risk": assertion, "auditor_conclusion": "",
        "library_codes": [r["code"] for r in recs], "score_caveat": SCORE_CAVEAT,
        "source": "template from Person 3's recommendation library (local LLM not used)",
    }


def memo(row, use_llm=False, model=None, language="English"):
    recs = recommend(row["rule_hits"], row["shap_top"])
    base = template_memo(row, recs)
    if use_llm:
        res = ask_llm(prompts.SYSTEM_AUDITOR.format(language=language), prompts.USER_MEMO.format(**_facts(row, recs)), model)
        if res and "why_suspicious" in res:
            res["auditor_conclusion"] = ""                       # always left to the human
            res.setdefault("evidence_to_obtain", base["evidence_to_obtain"])
            res["library_codes"], res["score_caveat"] = base["library_codes"], SCORE_CAVEAT
            res["source"] = f"{model or config.OLLAMA_MODEL} (local) - prompts {prompts.PROMPT_VERSION}"
            return res
    return base


def memo_text(m, row):
    """Working-paper text version (Person 3's memo layout)."""
    bullet = lambda xs: "\n".join(f"- {x}" for x in xs) or "- Not supplied"
    return f"""JOURNALGUARD AI - DRAFT AUDIT WORKING-PAPER MEMO

Entry details
- Entry ID: {row['entry_id']}
- Posting date: {row['posting_date']:%d/%m/%Y} | Entered: {row['entered_at']:%d/%m/%Y %H:%M}
- Amount: {row['amount']:,.2f} | User: {row['user']}
- Accounts: {row['accounts']}

Screening result
- Risk score: {row['risk_score']}/100 ({m.get('risk_level', '')})
- Red flags: {', '.join(row['rule_hits']) or 'none'}
- Interpretation: {m.get('score_caveat', SCORE_CAVEAT)}

Why it was flagged
{m.get('why_suspicious', '')}

Evidence to obtain
{bullet(m.get('evidence_to_obtain', []))}

Recommended audit procedures
{bullet(m.get('follow_up_procedures', []))}

Assertion at risk: {m.get('assertion_at_risk', '')}

Auditor conclusion
[To be completed by the auditor after obtaining and evaluating sufficient appropriate audit evidence.]

Generated by: {m.get('source', '')}. Draft - review, tailor and approve before inclusion in an audit file.
"""


def engagement_summary(facts, use_llm=False, model=None):
    if use_llm:
        res = ask_llm(prompts.SYSTEM_AUDITOR.format(language="English"), prompts.USER_SUMMARY.format(**facts), model)
        if res and "overview" in res:
            res["source"] = f"{model or config.OLLAMA_MODEL} (local)"
            return res
    gt = facts["ground_truth"]
    return {
        "overview": (f"We tested 100% of the ledger ({facts['n_entries']:,} entries, {facts['n_manual']:,} manual). "
                     f"{facts['n_alerts']:,} entries reached a risk score of {facts['cutoff']} or more, worth "
                     f"{facts['value_under_review']:,.0f} EUR under review (not a loss estimate). {gt}"),
        "key_themes": [f"{k}: {v} alerts" for k, v in facts["themes"].items()],
        "recommended_next_steps": ["Review the High alerts first and obtain the evidence listed in each memo",
                                   "Discuss late and weekend postings with the chief accountant",
                                   "Check the users and bank accounts behind cash and clearing alerts",
                                   "Extend the test to the next closing period"],
        "limitations": ["Risk scores prioritise audit attention; they are not probabilities of fraud",
                        "The ledger and its labels are synthetic: real fraud may look different",
                        "Thresholds and materiality are our assumptions",
                        "Template text - run the local LLM for a written summary"],
        "source": "template (local LLM not running)",
    }


def ask(question, alerts, use_llm=True, model=None, max_rows=60):
    """Natural-language question about the alerts (brief: 'natural-language querying of alerts')."""
    cols = ["entry_id", "risk_score", "posting_date", "user", "text", "amount", "theme", "rule_hits"]
    table = alerts[[c for c in cols if c in alerts]].head(max_rows).copy()
    table["rule_hits"] = table["rule_hits"].map(lambda x: "; ".join(x))
    if use_llm:
        res = ask_llm(prompts.SYSTEM_AUDITOR.format(language="English"),
                      prompts.USER_ASK.format(question=question, table=table.to_csv(index=False)), model)
        if res and "answer" in res:
            return res
    words = [w for w in question.lower().split() if len(w) > 3]
    hit = table[table.astype(str).apply(lambda r: any(w in " ".join(r).lower() for w in words), axis=1)]
    return {"answer": f"Local LLM not running. {len(hit)} alert(s) mention words from your question.",
            "entry_ids": hit["entry_id"].head(10).tolist()}
