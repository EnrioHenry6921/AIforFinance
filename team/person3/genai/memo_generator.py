"""Generate auditor-ready draft memos. Works without an LLM; Ollama is optional."""
from __future__ import annotations
import json
from .audit_recommendations import get_audit_recommendation
from .prompts import SYSTEM_PROMPT, MEMO_USER_TEMPLATE


def _as_text(value):
    return "Not supplied" if value is None else str(value)


def _deterministic_memo(rec):
    signals=rec["signals"]
    observations="\n".join(f"- {s['explanation']}" for s in signals)
    concerns="\n".join(f"- {s['potential_risk']}" for s in signals)
    evidence="\n".join(f"- {s['evidence_to_request']}" for s in signals)
    procedures="\n".join(f"- {s['audit_procedure']}" for s in signals)
    return f"""JOURNALGUARD AI — DRAFT AUDIT WORKING-PAPER MEMO

Entry details
- Entry ID: {rec['entry_id']}
- Posting date: {rec['posting_date']}
- Amount: {rec['amount']:,.2f}
- Accounts: {rec['accounts']}

Screening result
- Risk score: {rec['risk_score']}/100
- Risk level: {rec['risk_level']}
- Priority: {rec['priority']}
- Interpretation: {rec['score_caveat']}

Supported observations
{observations}

Potential audit concern
{concerns}

Evidence to obtain
{evidence}

Recommended audit procedures
{procedures}

Auditor conclusion
[To be completed by the auditor after obtaining and evaluating sufficient appropriate audit evidence.]

Prepared as an automated draft. Review, tailor and approve before inclusion in an audit file.
"""


def generate_audit_memo(entry, use_ollama=False, model="llama3.2"):
    """Return memo text. Optional Ollama rewrite is constrained by prompts.py."""
    rec=get_audit_recommendation(entry)
    memo=_deterministic_memo(rec)
    if not use_ollama:
        return memo
    try:
        import ollama
        response=ollama.chat(model=model, messages=[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":MEMO_USER_TEMPLATE.format(recommendation=json.dumps(rec,ensure_ascii=False,default=str))}
        ])
        content=response.get("message",{}).get("content","").strip()
        return content if content else memo
    except Exception:
        # Reliable fallback: LLM is an optional drafting layer, not a dependency.
        return memo
